import { useState } from 'react';
import * as yaml from 'js-yaml';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';

/** Plan §5.8 condition list: an array of Jinja2 boolean expression strings,
 * all of which must hold for the automation's action chain to run. */
export function ConditionBuilder({ onYamlChange }: { onYamlChange: (yamlText: string) => void }) {
  const [conditions, setConditions] = useState<string[]>([]);

  function emit(next: string[]) {
    setConditions(next);
    onYamlChange(next.length ? yaml.dump(next) : '');
  }

  return (
    <div className="space-y-2">
      {conditions.map((cond, idx) => (
        <div key={idx} className="flex items-center gap-2">
          <Input
            value={cond}
            onChange={(e) => emit(conditions.map((c, i) => (i === idx ? e.target.value : c)))}
            placeholder="{{ trigger.payload.fieldID in [1, 2, 3] }}"
          />
          <button onClick={() => emit(conditions.filter((_, i) => i !== idx))} className="text-vmd-textSubtle hover:text-vmd-danger">
            <Trash2 size={14} />
          </button>
        </div>
      ))}
      <Button onClick={() => emit([...conditions, ''])}>
        <Plus size={14} /> Add condition
      </Button>
    </div>
  );
}
