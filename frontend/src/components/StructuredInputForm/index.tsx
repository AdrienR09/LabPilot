import React from 'react';

export interface StructuredInput {
  type: 'select' | 'text' | 'number' | 'checkbox' | 'radio';
  id: string;
  label: string;
  description?: string;
  required?: boolean;
  options?: Array<{ label: string; value: string | number }>;
  placeholder?: string;
  value?: string | number | boolean;
}

export interface StructuredPrompt {
  message: string;
  inputs: StructuredInput[];
  submitLabel?: string;
}

interface StructuredInputFormProps {
  prompt: StructuredPrompt;
  onSubmit: (values: Record<string, string | number | boolean>) => void;
  isLoading?: boolean;
}

export function StructuredInputForm({ prompt, onSubmit, isLoading = false }: StructuredInputFormProps) {
  const [values, setValues] = React.useState<Record<string, string | number | boolean>>(() => {
    const initial: Record<string, string | number | boolean> = {};
    prompt.inputs.forEach(input => {
      initial[input.id] = input.value ?? (input.type === 'checkbox' ? false : '');
    });
    return initial;
  });

  const handleChange = (id: string, newValue: string | number | boolean) => {
    setValues(prev => ({ ...prev, [id]: newValue }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // Validate required fields
    const missingRequired = prompt.inputs.filter(
      input => input.required && !values[input.id]
    );

    if (missingRequired.length > 0) {
      alert(`Please fill in: ${missingRequired.map(i => i.label).join(', ')}`);
      return;
    }

    onSubmit(values);
  };

  return (
    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
      <p className="text-sm text-gray-700 dark:text-gray-300 mb-4">{prompt.message}</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        {prompt.inputs.map(input => (
          <div key={input.id}>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {input.label}
              {input.required && <span className="text-red-500 ml-1">*</span>}
            </label>
            {input.description && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{input.description}</p>
            )}

            {input.type === 'select' && (
              <select
                value={values[input.id] as string}
                onChange={e => handleChange(input.id, e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-600 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled={isLoading}
              >
                <option value="">Select an option...</option>
                {input.options?.map(opt => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            )}

            {input.type === 'text' && (
              <input
                type="text"
                value={values[input.id] as string}
                onChange={e => handleChange(input.id, e.target.value)}
                placeholder={input.placeholder}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-600 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled={isLoading}
              />
            )}

            {input.type === 'number' && (
              <input
                type="number"
                value={values[input.id] as number}
                onChange={e => handleChange(input.id, parseFloat(e.target.value) || 0)}
                placeholder={input.placeholder}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-600 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled={isLoading}
              />
            )}

            {input.type === 'checkbox' && (
              <input
                type="checkbox"
                checked={values[input.id] as boolean}
                onChange={e => handleChange(input.id, e.target.checked)}
                className="w-4 h-4 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-600 text-blue-600 focus:ring-2 focus:ring-blue-500"
                disabled={isLoading}
              />
            )}

            {input.type === 'radio' && input.options && (
              <fieldset className="space-y-2">
                {input.options.map(opt => (
                  <label key={opt.value} className="flex items-center cursor-pointer">
                    <input
                      type="radio"
                      name={input.id}
                      value={opt.value}
                      checked={values[input.id] === opt.value}
                      onChange={e => handleChange(input.id, e.target.value)}
                      className="w-4 h-4 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-600 text-blue-600 focus:ring-2 focus:ring-blue-500"
                      disabled={isLoading}
                    />
                    <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">{opt.label}</span>
                  </label>
                ))}
              </fieldset>
            )}
          </div>
        ))}

        <button
          type="submit"
          disabled={isLoading}
          className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Sending...' : prompt.submitLabel || 'Submit'}
        </button>
      </form>
    </div>
  );
}
