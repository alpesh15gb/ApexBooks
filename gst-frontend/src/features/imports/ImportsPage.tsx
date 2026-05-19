import { useState, useCallback, useRef, useEffect } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { CardSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { CheckCircle, XCircle, Upload, FileText, AlertTriangle, Database, Download } from 'lucide-react';
import { apiErrorToString } from '@/utils/validation';
import toast from 'react-hot-toast';
import { getAccessToken } from '@/lib/api';

function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getAccessToken();
  return fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': token ? `Bearer ${token}` : '',
    },
  });
}

interface ImportFormat {
  id: string;
  name: string;
  extensions: string[];
  description: string;
  available: boolean;
}

export function ImportsPage() {
  const [formats, setFormats] = useState<ImportFormat[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedFormat, setSelectedFormat] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [step, setStep] = useState<'select' | 'preview' | 'done'>('select');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch formats on mount
  useEffect(() => {
    authFetch('/api/v1/import/formats')
      .then(r => r.json())
      .then(d => setFormats(d?.data?.formats || []))
      .catch(() => toast.error('Could not load import formats'))
      .finally(() => setLoading(false));
  }, []);

  const selectedFmt = formats.find(f => f.id === selectedFormat);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => setDragging(false), []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      const ext = '.' + droppedFile.name.split('.').pop()?.toLowerCase();
      if (selectedFmt && !selectedFmt.extensions.includes(ext)) {
        toast.error(`Expected ${selectedFmt.extensions.join(', ')}, got ${ext}`);
        return;
      }
      setFile(droppedFile);
    }
  }, [selectedFmt]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) setFile(e.target.files[0]);
  }, []);

  const handleDryRun = useCallback(async () => {
    if (!file || !selectedFormat) return;
    setImporting(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('import_format', selectedFormat);
      const res = await authFetch('/api/v1/import/dry-run', { method: 'POST', body: formData });
      const json = await res.json();
      if (json.success) {
        setResult({ ...json.data, dryRun: true });
        setStep('preview');
      } else {
        toast.error(json.error?.message || 'Dry run failed');
      }
    } catch (err) {
      toast.error(apiErrorToString(err));
    } finally {
      setImporting(false);
    }
  }, [file, selectedFormat]);

  const handleImport = useCallback(async () => {
    if (!file || !selectedFormat) return;
    setImporting(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('import_format', selectedFormat);
      const res = await authFetch('/api/v1/import/upload', { method: 'POST', body: formData });
      const json = await res.json();
      if (json.success) {
        setResult({ ...json.data, dryRun: false });
        setStep('done');
        toast.success('Import completed');
      } else {
        toast.error(json.error?.message || 'Import failed');
      }
    } catch (err) {
      toast.error(apiErrorToString(err));
    } finally {
      setImporting(false);
    }
  }, [file, selectedFormat]);

  const reset = () => {
    setFile(null);
    setResult(null);
    setStep('select');
    setSelectedFormat('');
  };

  if (loading) return <CardSkeleton count={3} />;

  return (
    <div className="space-y-6">
      <PageHeader title="Import Data" subtitle="Import from Vyapar, Tally, and other accounting software" />

      {/* Step 1: Select Format & Upload */}
      {step === 'select' && (
        <div className="space-y-6">
          {/* Format Selection */}
          <div className="card">
            <div className="card-header">
              <h3 className="font-semibold text-gray-900">Select Source Format</h3>
            </div>
            <div className="card-body">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {formats.map(fmt => (
                  <button
                    key={fmt.id}
                    onClick={() => { setSelectedFormat(fmt.id); setFile(null); }}
                    className={`text-left p-4 rounded-lg border-2 transition-all ${
                      selectedFormat === fmt.id
                        ? 'border-brand-500 bg-brand-50 shadow-sm'
                        : fmt.available
                          ? 'border-gray-200 hover:border-brand-300 hover:bg-gray-50'
                          : 'border-gray-100 bg-gray-50 opacity-60 cursor-not-allowed'
                    }`}
                    disabled={!fmt.available}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`p-2 rounded-lg ${selectedFormat === fmt.id ? 'bg-brand-100' : 'bg-gray-100'}`}>
                        <Database className={`h-5 w-5 ${selectedFormat === fmt.id ? 'text-brand-600' : 'text-gray-500'}`} />
                      </div>
                      <div className="flex-1">
                        <p className="font-medium text-gray-900">{fmt.name}</p>
                        <p className="text-xs text-gray-500 mt-0.5">{fmt.description}</p>
                        <p className="text-xs text-gray-400 mt-1">{fmt.extensions.join(', ')}</p>
                      </div>
                      {!fmt.available && (
                        <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">Coming Soon</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {selectedFmt && (
            <div className="card">
              <div className="card-header">
                <h3 className="font-semibold text-gray-900">Upload File</h3>
                <p className="text-sm text-gray-500">{selectedFmt.name} — {selectedFmt.extensions.join(', ')}</p>
              </div>
              <div className="card-body">
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
                    dragging ? 'border-brand-500 bg-brand-50' : 'border-gray-300 hover:border-gray-400'
                  }`}
                >
                  <input ref={fileInputRef} type="file" accept={selectedFmt.extensions.join(',')} onChange={handleFileSelect} className="hidden" />
                  {file ? (
                    <div className="space-y-2">
                      <FileText className="h-10 w-10 text-brand-600 mx-auto" />
                      <p className="font-medium text-gray-900">{file.name}</p>
                      <p className="text-sm text-gray-500">{(file.size / 1024).toFixed(0)} KB</p>
                      <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setFile(null); }}>Remove</Button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <Upload className="h-10 w-10 text-gray-400 mx-auto" />
                      <p className="font-medium text-gray-700">Drop your {selectedFmt.name} file here</p>
                      <p className="text-sm text-gray-500">or click to browse</p>
                    </div>
                  )}
                </div>

                {file && (
                  <div className="flex justify-end gap-3 mt-4">
                    <Button variant="secondary" onClick={handleDryRun} loading={importing}>
                      <FileText className="h-4 w-4" /> Preview
                    </Button>
                    <Button onClick={handleImport} loading={importing}>
                      <Database className="h-4 w-4" /> Import Now
                    </Button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Step 2: Preview / Results */}
      {(step === 'preview' || step === 'done') && result && (
        <div className="space-y-6">
          <div className="card">
            <div className="card-header flex items-center justify-between">
              <h3 className="font-semibold text-gray-900">
                {result.dryRun ? 'Import Preview' : 'Import Results'}
              </h3>
              <Button variant="ghost" size="sm" onClick={reset}>
                <XCircle className="h-4 w-4" /> Start Over
              </Button>
            </div>
            <div className="card-body">
              {/* Stats Grid */}
              {result.stats && (
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
                  {Object.entries(result.stats).map(([key, val]) => (
                    <div key={key} className="bg-gray-50 rounded-lg p-4 text-center border border-gray-200">
                      <p className="text-2xl font-bold text-gray-900">{String(val)}</p>
                      <p className="text-xs text-gray-500 uppercase tracking-wider mt-1">
                        {key.replace(/_/g, ' ')}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {/* Status */}
              {!result.dryRun && (
                <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 flex items-center gap-3">
                  <CheckCircle className="h-6 w-6 text-emerald-600" />
                  <div>
                    <p className="font-medium text-emerald-800">Import Successful</p>
                    <p className="text-sm text-emerald-700">Data has been imported into your account.</p>
                  </div>
                </div>
              )}

              {result.dryRun && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center gap-3">
                  <AlertTriangle className="h-6 w-6 text-blue-600" />
                  <div>
                    <p className="font-medium text-blue-800">This is a preview — no data has been imported</p>
                    <p className="text-sm text-blue-700">Review the details below, then click Import to proceed.</p>
                  </div>
                </div>
              )}

              {/* Transaction Breakdown */}
              {result.type_breakdown && (
                <div className="mt-6">
                  <h4 className="text-sm font-medium text-gray-700 mb-3">Transaction Breakdown</h4>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                          <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Count</th>
                          <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Total</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {result.type_breakdown.map((b: any, i: number) => (
                          <tr key={i}>
                            <td className="px-4 py-2 text-gray-900">{b.txn_type}</td>
                            <td className="px-4 py-2 text-right">{b.count}</td>
                            <td className="px-4 py-2 text-right font-medium">₹{Number(b.total || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex justify-end gap-3 mt-6">
                <Button variant="secondary" onClick={reset}>Start Over</Button>
                {result.dryRun && (
                  <Button onClick={handleImport} loading={importing}>
                    <Database className="h-4 w-4" /> Confirm Import
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Logos for supported apps */}
      <div className="card">
        <div className="card-header">
          <h3 className="font-semibold text-gray-900">Supported Import Sources</h3>
        </div>
        <div className="card-body">
          <div className="flex flex-wrap gap-6 items-center">
            {formats.map(fmt => (
              <div key={fmt.id} className={`flex items-center gap-2 px-4 py-2 rounded-lg border ${fmt.available ? 'border-gray-200' : 'border-dashed border-gray-200 opacity-50'}`}>
                <Database className={`h-5 w-5 ${fmt.available ? 'text-brand-600' : 'text-gray-400'}`} />
                <div>
                  <p className="text-sm font-medium text-gray-900">{fmt.name}</p>
                  <p className="text-xs text-gray-400">{fmt.available ? 'Available' : 'Coming Soon'}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
