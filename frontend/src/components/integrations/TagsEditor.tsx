import { useState } from 'react';
import { X } from 'lucide-react';
import { Input } from '../ui/Input';
import { Chip } from '../ui/Badge';

/** Inline tag editor (plan §6: "no separate tag management page — tags are
 * ad-hoc strings"). Used on every entity's config form. */
export function TagsEditor({
  tags,
  onChange,
  disabled,
}: {
  tags: string[];
  onChange: (tags: string[]) => void;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState('');

  function addTag() {
    const value = draft.trim();
    if (value && !tags.includes(value)) onChange([...tags, value]);
    setDraft('');
  }

  return (
    <div>
      <div className="mb-1.5 flex flex-wrap gap-1.5">
        {tags.map((tag) => (
          <Chip key={tag}>
            {tag}
            {!disabled && (
              <button onClick={() => onChange(tags.filter((t) => t !== tag))} className="ml-1.5">
                <X size={12} />
              </button>
            )}
          </Chip>
        ))}
      </div>
      {!disabled && (
        <Input
          placeholder="Add tag and press Enter"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addTag();
            }
          }}
          onBlur={addTag}
        />
      )}
    </div>
  );
}
