import React from 'react';
import clsx from 'clsx';

interface ParameterInputProps {
  name: string;
  value: any;
  onChange: (value: any) => void;
  type?: 'number' | 'text' | 'select' | 'boolean';
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
  disabled?: boolean;
}

export const ParameterInput: React.FC<ParameterInputProps> = ({
  name,
  value,
  onChange,
  type = 'number',
  unit,
  min,
  max,
  step,
  options,
  disabled = false,
}) => {
  return (
    <div className="flex flex-col space-y-1">
      <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
        {name}
      </label>
      {type === 'select' ? (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={clsx(
            'px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md',
            'bg-white dark:bg-gray-700 text-gray-900 dark:text-white',
            'focus:outline-none focus:ring-2 focus:ring-blue-500',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        >
          {options?.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : type === 'boolean' ? (
        <input
          type="checkbox"
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
          disabled={disabled}
          className="w-5 h-5"
        />
      ) : (
        <div className="flex items-center space-x-2">
          <input
            type={type}
            value={value}
            onChange={(e) => onChange(type === 'number' ? parseFloat(e.target.value) : e.target.value)}
            min={min}
            max={max}
            step={step}
            disabled={disabled}
            className={clsx(
              'flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md',
              'bg-white dark:bg-gray-700 text-gray-900 dark:text-white',
              'focus:outline-none focus:ring-2 focus:ring-blue-500',
              disabled && 'opacity-50 cursor-not-allowed'
            )}
          />
          {unit && <span className="text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">{unit}</span>}
        </div>
      )}
    </div>
  );
};

interface ParameterGridProps {
  parameters: Record<string, any>;
  onParameterChange?: (key: string, value: any) => void;
  disabled?: boolean;
}

export const ParameterGrid: React.FC<ParameterGridProps> = ({
  parameters,
  onParameterChange,
  disabled = false,
}) => {
  return (
    <div className="grid grid-cols-2 gap-4">
      {Object.entries(parameters).map(([key, param]) => (
        <ParameterInput
          key={key}
          name={param.name || key}
          value={param.value}
          onChange={(val) => onParameterChange?.(key, val)}
          type={param.type}
          unit={param.unit}
          min={param.min}
          max={param.max}
          step={param.step}
          options={param.options}
          disabled={disabled}
        />
      ))}
    </div>
  );
};

interface ActionButtonProps {
  label: string;
  onClick: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  loading?: boolean;
}

export const ActionButton: React.FC<ActionButtonProps> = ({
  label,
  onClick,
  variant = 'primary',
  disabled = false,
  loading = false,
}) => {
  const variantClasses = {
    primary: 'bg-blue-600 hover:bg-blue-700 text-white',
    secondary: 'bg-gray-300 dark:bg-gray-600 text-gray-900 dark:text-white hover:bg-gray-400 dark:hover:bg-gray-500',
    danger: 'bg-red-600 hover:bg-red-700 text-white',
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={clsx(
        'px-4 py-2 rounded-md font-medium transition-colors',
        variantClasses[variant],
        (disabled || loading) && 'opacity-50 cursor-not-allowed'
      )}
    >
      {loading ? 'Loading...' : label}
    </button>
  );
};

interface DataDisplayProps {
  label: string;
  value: any;
  unit?: string;
  precision?: number;
}

export const DataDisplay: React.FC<DataDisplayProps> = ({
  label,
  value,
  unit,
  precision = 2,
}) => {
  let displayValue = value;
  if (typeof value === 'number') {
    displayValue = value.toFixed(precision);
  }

  return (
    <div className="bg-gray-100 dark:bg-gray-700 rounded-md p-3">
      <div className="text-sm text-gray-600 dark:text-gray-400">{label}</div>
      <div className="text-lg font-semibold text-gray-900 dark:text-white">
        {displayValue} {unit}
      </div>
    </div>
  );
};

interface StatusIndicatorProps {
  connected: boolean;
  showLabel?: boolean;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  connected,
  showLabel = true,
}) => {
  return (
    <div className="flex items-center space-x-2">
      <div
        className={clsx(
          'w-3 h-3 rounded-full',
          connected ? 'bg-green-500' : 'bg-red-500'
        )}
      />
      {showLabel && (
        <span className={clsx(
          'text-sm font-medium',
          connected ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
        )}>
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      )}
    </div>
  );
};

interface ConnectDisconnectPanelProps {
  connected: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  loading?: boolean;
}

export const ConnectDisconnectPanel: React.FC<ConnectDisconnectPanelProps> = ({
  connected,
  onConnect,
  onDisconnect,
  loading = false,
}) => {
  return (
    <div className="border-t border-gray-200 dark:border-gray-700 pt-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Device Status</span>
        <StatusIndicator connected={connected} />
      </div>
      <div className="flex space-x-3">
        {!connected ? (
          <ActionButton
            label="Connect"
            onClick={onConnect}
            variant="primary"
            loading={loading}
          />
        ) : (
          <ActionButton
            label="Disconnect"
            onClick={onDisconnect}
            variant="danger"
            loading={loading}
          />
        )}
      </div>
    </div>
  );
};
