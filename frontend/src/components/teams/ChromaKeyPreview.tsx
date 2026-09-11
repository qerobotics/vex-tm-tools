import { useEffect, useRef } from 'react';

const VERTEX_SRC = `
attribute vec2 aPosition;
varying vec2 vTexCoord;
void main() {
  vTexCoord = vec2((aPosition.x + 1.0) / 2.0, (1.0 - aPosition.y) / 2.0);
  gl_Position = vec4(aPosition, 0.0, 1.0);
}
`;

// Chroma-key fragment shader: mirrors the backend's FFmpeg `colorkey=color:similarity:blend`
// filter (plan §5.13/Appendix A.5) closely enough to give the operator an accurate live
// preview of what FFmpeg will actually produce, without running FFmpeg client-side.
const FRAGMENT_SRC = `
precision mediump float;
varying vec2 vTexCoord;
uniform sampler2D uSampler;
uniform vec3 uKeyColor;
uniform float uSimilarity;
uniform float uBlend;

void main() {
  vec4 color = texture2D(uSampler, vTexCoord);
  float dist = distance(color.rgb, uKeyColor);
  float edge0 = uSimilarity;
  float edge1 = uSimilarity + uBlend + 0.0001;
  float alpha = smoothstep(edge0, edge1, dist);
  gl_FragColor = vec4(color.rgb, alpha);
}
`;

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '');
  const num = parseInt(clean, 16);
  return [((num >> 16) & 255) / 255, ((num >> 8) & 255) / 255, (num & 255) / 255];
}

function compileShader(gl: WebGLRenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type)!;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const info = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`Shader compile error: ${info}`);
  }
  return shader;
}

export interface ChromaKeyParams {
  keyColour: string;
  similarity: number;
  blend: number;
}

/**
 * Live WebGL chroma-key preview (plan §5.13/§12 Teams page). Renders the
 * given local video `File` through a chroma-key fragment shader onto a
 * checkerboard-backed canvas so keyed-out (transparent) regions are
 * visible, updating live as `params` change — this never touches the
 * server; the actual keying happens server-side via FFmpeg once "Process &
 * Upload" is clicked (`useUploadTeamVideo`).
 */
export function ChromaKeyPreview({ file, params }: { file: File | null; params: ChromaKeyParams }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const paramsRef = useRef(params);
  paramsRef.current = params;

  useEffect(() => {
    if (!file) return undefined;
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const gl = canvas.getContext('webgl');
    if (!gl) return undefined;

    const video = document.createElement('video');
    video.muted = true;
    video.loop = true;
    video.playsInline = true;
    video.src = URL.createObjectURL(file);
    videoRef.current = video;
    void video.play().catch(() => {
      /* Autoplay can be blocked until user interaction; the preview will
       * start once the browser allows it (or the user taps the canvas). */
    });

    const program = gl.createProgram()!;
    gl.attachShader(program, compileShader(gl, gl.VERTEX_SHADER, VERTEX_SRC));
    gl.attachShader(program, compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SRC));
    gl.linkProgram(program);
    gl.useProgram(program);

    const positionBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
      gl.STATIC_DRAW,
    );
    const positionLoc = gl.getAttribLocation(program, 'aPosition');
    gl.enableVertexAttribArray(positionLoc);
    gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);

    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    const uKeyColor = gl.getUniformLocation(program, 'uKeyColor');
    const uSimilarity = gl.getUniformLocation(program, 'uSimilarity');
    const uBlend = gl.getUniformLocation(program, 'uBlend');

    let raf = 0;
    function render() {
      if (!gl || video.readyState < video.HAVE_CURRENT_DATA) {
        raf = requestAnimationFrame(render);
        return;
      }
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);

      const [r, g, b] = hexToRgb(paramsRef.current.keyColour);
      gl.uniform3f(uKeyColor, r, g, b);
      gl.uniform1f(uSimilarity, paramsRef.current.similarity);
      gl.uniform1f(uBlend, paramsRef.current.blend);

      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      raf = requestAnimationFrame(render);
    }
    render();

    return () => {
      cancelAnimationFrame(raf);
      video.pause();
      URL.revokeObjectURL(video.src);
    };
  }, [file]);

  return (
    <div
      className="relative overflow-hidden rounded-lg border border-vmd-border"
      style={{
        backgroundImage:
          'linear-gradient(45deg, #222 25%, transparent 25%), linear-gradient(-45deg, #222 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #222 75%), linear-gradient(-45deg, transparent 75%, #222 75%)',
        backgroundSize: '20px 20px',
        backgroundPosition: '0 0, 0 10px, 10px -10px, -10px 0px',
      }}
    >
      {file ? (
        <canvas ref={canvasRef} width={480} height={270} className="block w-full" />
      ) : (
        <div className="flex h-40 items-center justify-center text-sm text-vmd-textSubtle">
          Select a video to preview chroma keying
        </div>
      )}
    </div>
  );
}
