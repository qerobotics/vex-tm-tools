import { useState } from 'react';
import { ChromaKeyPreview } from './ChromaKeyPreview';
import { useUploadTeamVideo, useVideoStatus } from '../../api/teams';
import { usePermission } from '../../hooks/usePermission';
import { useUiStore } from '../../stores/ui';
import { Button } from '../ui/Button';
import { Input, Label } from '../ui/Input';

export function VideoUploader({ teamNumber }: { teamNumber: string }) {
  const canUpload = usePermission('video:upload');
  const upload = useUploadTeamVideo();
  const { data: status } = useVideoStatus(teamNumber, { pollWhileProcessing: true });
  const pushToast = useUiStore((s) => s.pushToast);

  const [file, setFile] = useState<File | null>(null);
  const [keyColour, setKeyColour] = useState('#00B140');
  const [similarity, setSimilarity] = useState(0.1);
  const [blend, setBlend] = useState(0.05);

  function handleUpload() {
    if (!file) return;
    upload.mutate(
      { number: teamNumber, file, keyColour, similarity, blend },
      {
        onSuccess: () => pushToast('Upload accepted — processing…', 'success'),
        onError: (err) => pushToast(err instanceof Error ? err.message : 'Upload failed', 'error'),
      },
    );
  }

  return (
    <div className="space-y-3">
      <ChromaKeyPreview file={file} params={{ keyColour, similarity, blend }} />

      {canUpload && (
        <>
          <div>
            <Label>Robot video (.mp4 / .mov)</Label>
            <Input type="file" accept=".mp4,.mov,video/mp4,video/quicktime" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label>Key Colour</Label>
              <input
                type="color"
                value={keyColour}
                onChange={(e) => setKeyColour(e.target.value)}
                className="h-9 w-full rounded-lg border border-vmd-border bg-vmd-elevated"
              />
            </div>
            <div>
              <Label>Similarity ({similarity.toFixed(2)})</Label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={similarity}
                onChange={(e) => setSimilarity(Number(e.target.value))}
                className="w-full"
              />
            </div>
            <div>
              <Label>Blend ({blend.toFixed(2)})</Label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={blend}
                onChange={(e) => setBlend(Number(e.target.value))}
                className="w-full"
              />
            </div>
          </div>
          <Button variant="primary" onClick={handleUpload} disabled={!file || upload.isPending}>
            {upload.isPending ? 'Uploading…' : 'Process & Upload'}
          </Button>
        </>
      )}

      {status && (
        <p className="text-sm text-vmd-textMuted">
          Processing status: <span className="font-medium text-vmd-textStrong">{status.video_processing_status}</span>
          {status.video_processing_status === 'DONE' && status.video_360_s3_key && ' — stored in S3.'}
        </p>
      )}

      <p className="text-xs text-vmd-textSubtle">
        Note: the backend's Teams router (plan §5.13/Appendix A.5) exposes upload +
        status-polling but no dedicated "Re-process without re-upload" endpoint yet — the
        raw video is retained in S3 server-side, but re-keying it currently requires
        re-uploading the same file with new slider values.
      </p>
    </div>
  );
}
