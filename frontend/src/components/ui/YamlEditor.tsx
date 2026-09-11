import { Textarea } from './Input';

export function YamlEditor({
  value,
  onChange,
  rows = 10,
  readOnly,
}: {
  value: string;
  onChange?: (value: string) => void;
  rows?: number;
  readOnly?: boolean;
}) {
  return (
    <Textarea
      className="vmd-code-block w-full text-xs leading-relaxed"
      rows={rows}
      value={value}
      readOnly={readOnly}
      onChange={(e) => onChange?.(e.target.value)}
      spellCheck={false}
    />
  );
}
