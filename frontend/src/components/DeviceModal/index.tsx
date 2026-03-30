import React, { useState, useMemo } from 'react';
import { useLabPilotStore } from '@/store';
import {
  getManufacturers,
  getCategoriesByManufacturer,
  getInstrumentsByManufacturerAndCategory,
  getInstrumentById,
} from '@/data/instruments';
import clsx from 'clsx';

interface DeviceModalProps {
  isOpen: boolean;
  availableAdapters?: Array<{ name: string; type: string; category: string }>;
}

export function DeviceModal({ isOpen }: DeviceModalProps) {
  const { connectDevice, devicesLoading, devicesError, hideDeviceModal } = useLabPilotStore();
  const [step, setStep] = useState<'manufacturer' | 'category' | 'model' | 'connect'>('manufacturer');

  // Selection state
  const [selectedManufacturer, setSelectedManufacturer] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [selectedModel, setSelectedModel] = useState<any>(null);
  const [customName, setCustomName] = useState('');

  if (!isOpen) return null;

  // Get dynamic lists based on selections
  const manufacturers = useMemo(() => getManufacturers(), []);
  const categories = useMemo(() =>
    selectedManufacturer ? getCategoriesByManufacturer(selectedManufacturer) : [],
    [selectedManufacturer]
  );
  const models = useMemo(() =>
    selectedManufacturer && selectedCategory
      ? getInstrumentsByManufacturerAndCategory(selectedManufacturer, selectedCategory)
      : [],
    [selectedManufacturer, selectedCategory]
  );

  const handleManufacturerSelect = (mfr: string) => {
    setSelectedManufacturer(mfr);
    setSelectedCategory('');
    setSelectedModel(null);
    setStep('category');
  };

  const handleCategorySelect = (cat: string) => {
    setSelectedCategory(cat);
    setSelectedModel(null);
    setStep('model');
  };

  const handleModelSelect = (model: any) => {
    setSelectedModel(model);
    setCustomName(model.name);
    setStep('connect');
  };

  const handleConnect = async () => {
    if (!customName || !selectedModel) return;

    await connectDevice(customName, selectedModel.adapterType, {
      manufacturer: selectedModel.manufacturer,
      model: selectedModel.modelNumber,
    });

    // Reset form
    setStep('manufacturer');
    setSelectedManufacturer('');
    setSelectedCategory('');
    setSelectedModel(null);
    setCustomName('');
  };

  const handleBack = () => {
    if (step === 'category') {
      setStep('manufacturer');
      setSelectedCategory('');
    } else if (step === 'model') {
      setStep('category');
      setSelectedModel(null);
    } else if (step === 'connect') {
      setStep('model');
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg max-w-lg w-full mx-4">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                {step === 'manufacturer' && 'Select Manufacturer'}
                {step === 'category' && 'Select Category'}
                {step === 'model' && 'Select Model'}
                {step === 'connect' && 'Connect Device'}
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Step {['manufacturer', 'category', 'model', 'connect'].indexOf(step) + 1} of 4
              </p>
            </div>
          </div>
        </div>

        <div className="p-6 space-y-5">
          {devicesError && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded text-sm">
              {devicesError}
            </div>
          )}

          {/* Step 1: Manufacturer Selection */}
          {step === 'manufacturer' && (
            <div className="space-y-3">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Choose Manufacturer
              </label>
              <div className="grid grid-cols-2 gap-2 max-h-60 overflow-y-auto">
                {manufacturers.map((mfr) => (
                  <button
                    key={mfr}
                    onClick={() => handleManufacturerSelect(mfr)}
                    className={clsx(
                      'px-4 py-3 rounded-lg border-2 transition-all text-sm font-medium text-left',
                      selectedManufacturer === mfr
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                        : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                    )}
                  >
                    {mfr}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Category Selection */}
          {step === 'category' && (
            <div className="space-y-3">
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm">
                <span className="text-blue-700 dark:text-blue-300">
                  ✓ Manufacturer: <strong>{selectedManufacturer}</strong>
                </span>
              </div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Choose Category
              </label>
              <div className="grid grid-cols-2 gap-2 max-h-60 overflow-y-auto">
                {categories.map((cat) => (
                  <button
                    key={cat}
                    onClick={() => handleCategorySelect(cat)}
                    className={clsx(
                      'px-4 py-3 rounded-lg border-2 transition-all text-sm font-medium text-left',
                      selectedCategory === cat
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                        : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                    )}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 3: Model Selection */}
          {step === 'model' && (
            <div className="space-y-3">
              <div className="space-y-1 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm">
                <div className="text-blue-700 dark:text-blue-300">
                  ✓ Manufacturer: <strong>{selectedManufacturer}</strong>
                </div>
                <div className="text-blue-700 dark:text-blue-300">
                  ✓ Category: <strong>{selectedCategory}</strong>
                </div>
              </div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Select Model
              </label>
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {models.map((model) => (
                  <button
                    key={model.id}
                    onClick={() => handleModelSelect(model)}
                    className={clsx(
                      'w-full px-4 py-3 rounded-lg border-2 transition-all text-left',
                      selectedModel?.id === model.id
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                        : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                    )}
                  >
                    <div className="font-medium text-gray-900 dark:text-white">
                      {model.name}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      {model.modelNumber} • {model.dimensionality}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 4: Device Connection */}
          {step === 'connect' && selectedModel && (
            <div className="space-y-4">
              <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <div className="space-y-2">
                  <div className="text-sm text-blue-700 dark:text-blue-300">
                    ✓ <strong>{selectedModel.manufacturer}</strong> - <strong>{selectedModel.category}</strong>
                  </div>
                  <div className="text-lg font-semibold text-gray-900 dark:text-white">
                    {selectedModel.name}
                  </div>
                  <div className="text-xs text-gray-600 dark:text-gray-400">
                    {selectedModel.modelNumber}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                    {selectedModel.description}
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Device Name (optional)
                </label>
                <input
                  type="text"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder={selectedModel.name}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  disabled={devicesLoading}
                />
              </div>
            </div>
          )}

          {/* Buttons */}
          <div className="flex gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              type="button"
              onClick={step === 'manufacturer' ? hideDeviceModal : handleBack}
              className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700/50 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={devicesLoading}
            >
              {step === 'manufacturer' ? 'Cancel' : 'Back'}
            </button>
            <button
              type="button"
              onClick={
                step === 'manufacturer' || step === 'category' || step === 'model'
                  ? () => {} // Navigation handled by select clicks
                  : handleConnect
              }
              disabled={step === 'connect' ? (devicesLoading || !customName || !selectedModel) : true}
              className={clsx(
                'flex-1 px-4 py-2 rounded-md font-medium transition-colors flex items-center justify-center gap-2',
                step === 'connect' && !devicesLoading && customName && selectedModel
                  ? 'bg-blue-600 hover:bg-blue-700 text-white'
                  : 'bg-gray-300 dark:bg-gray-600 text-gray-600 dark:text-gray-400 cursor-not-allowed'
              )}
            >
              {devicesLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Connecting...
                </>
              ) : step === 'connect' ? (
                'Connect Device'
              ) : (
                'Next'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

