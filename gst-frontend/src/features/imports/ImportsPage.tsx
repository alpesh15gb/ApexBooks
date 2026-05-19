import { useState, useCallback, useRef, useEffect } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { CardSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { CheckCircle, XCircle, Upload, FileText, AlertTriangle, Database, Download, FileSpreadsheet } from 'lucide-react';
import { apiErrorToString } from '@/utils/validation';
import toast from 'react-hot-toast';
import { getAccessToken } from '@/lib/api';

function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getAccessToken();
  return fetch(url, {
    ...options,
    headers: {
      ...options.headers as Record<string, string>,
      'Authorization': token ? `Bearer ${token}` : '',
    },
  });
}

interface ImportTemplate {
  id: string;
  name: string;
  description: string;
  available: boolean;
  extensions: string[];
}

export function ImportsPage() {
  const [templates, setTemplates] = useState<ImportTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [step, setStep] = useState<'select' | 'preview' | 'done'>('select');
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    authFetch('/api/v1/import/formats')
      .then(r => r.json())
      .then(d => setTemplates(d?.data?.formats || []))
      .catch(() => toast.error('Could not load import templates'))
      .finally(() => setLoading(false));
  }, []);

  const selectedTpl = templates.find(t => t.id === selectedTemplate);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) setFile(e.target.files[0]);
  }, []);

  const handlePreview = useCallback(async () => {
    if (!file || !selectedTemplate) return;
    setImporting(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('template_id', selectedTemplate);
      formData.append('dry_run', 'true');
      const res = await authFetch('/api/v1/import/upload', { method: 'POST', body: formData });
      const json = await res.json();
      if (json.success) {
        setResult({ ...json.data, dryRun: true });
        setStep('preview');
      } else {
        toast.error(json.error?.message || 'Preview failed');
      }
    } catch (err) {
      toast.error(apiErrorToString(err));
    } finally {
      setImporting(false);
    }
  }, [file, selectedTemplate]);

  const handleImport = useCallback(async () => {
    if (!file || !selectedTemplate) return;
    setImporting(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('template_id', selectedTemplate);
      formData.append('dry_run', 'false');
      const res = await authFetch('/api/v1/import/upload', { method: 'POST', body: formData });
      const json = await res.json();
      if (json.success) {
        setResult({ ...json.data, dryRun: false });
        setStep('done');
        toast.success(`Imported ${json.data?.imported || 0} records`);
      } else {
        toast.error(json.error?.message || 'Import failed');
      }
    } catch (err) {
      toast.error(apiErrorToString(err));
    } finally {
      setImporting(false);
    }
  }, [file, selectedTemplate]);

  const downloadTemplate = useCallback((id: string) => {
    authFetch(`/api/v1/import/template/${id}`)
      .then(r => r.blob())
      .then(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${id}_template.csv`;
        a.click();
        URL.revokeObjectURL(url);
        toast.success('Template downloaded');
      })
      .catch(() => toast.error('Failed to download template'));
  }, []);

  const reset = () => {
    setFile(null);
    setResult(null);
    setStep('select');
    setSelectedTemplate('');
  };

  if (loading) return <CardSkeleton count={3} />;

  return (
    <div className="space-y-6">
      <PageHeader title="Import Data" subtitle="Import from CSV files using downloadable templates" />

      {step === 'select' && (
        <div className="space-y-6">
          <div className="card">
            <div className="card-header">
              <h3 className="font-semibold text-gray-900">Select Data Type</h3>
            </div>
            <div className="card-body">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {templates.map(tpl => (
                  <button
                    key={tpl.id}
                    onClick={() => { setSelectedTemplate(tpl.id); setFile(null); }}
                    className={`text-left p-4 rounded-lg border-2 transition-all ${
                      selectedTemplate === tpl.id
                        ? 'border-brand-500 bg-brand-50 shadow-sm'
                        : 'border-gray-200 hover:border-brand-300 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`p-2 rounded-lg ${selectedTemplate === tpl.id ? 'bg-brand-100' : 'bg-gray-100'}`}>
                        <FileSpreadsheet className={`h-5 w-5 ${selectedTemplate === tpl.id ? 'text-brand-600' : 'text-gray-500'}`} />
                      </div>
                      <div className="flex-1">
                        <p className="font-medium text-gray-900">{tpl.name}</p>
                        <p className="text-xs text-gray-500 mt-0.5">{tpl.description}</p>
                      </div>
                      <button
                        onClick={(e) => { e.stopPropagation(); downloadTemplate(tpl.id); }}
                        className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
                        title="Download template"
                      >
                        <Download className="h-4 w-4" />
                      </button>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {selectedTpl && (
            <div className="card">
              <div className="card-header flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-gray-900">Upload {selectedTpl.name} CSV</h3>
                  <p className="text-sm text-gray-500">Download the template first, fill it in, then upload</p>
                </div>
                <Button variant="secondary" size="sm" onClick={() => downloadTemplate(selectedTemplate)}>
                  <Download className="h-4 w-4" /> Download Template
                </Button>
              </div>
              <div className="card-body">
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed rounded-xl p-12 text-center cursor-pointer hover:border-gray-400 transition-colors"
                >
                  <input ref={fileInputRef} type="file" accept=".csv" onChange={handleFileSelect} className="hidden" />
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
                      <p className="font-medium text-gray-700">Drop your CSV file here or click to browse</p>
                      <p className="text-sm text-gray-500">.csv files only</p>
                    </div>
                  )}
                </div>

                {file && (
                  <div className="flex justify-end gap-3 mt-4">
                    <Button variant="secondary" onClick={handlePreview} loading={importing}>
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
              {result.preview && result.dryRun && (
                <div className="space-y-4">
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center gap-3">
                    <AlertTriangle className="h-6 w-6 text-blue-600" />
                    <div>
                      <p className="font-medium text-blue-800">Preview: {result.total_rows} rows found</p>
                      <p className="text-sm text-blue-700">Review the first {result.sample_size} rows below</p>
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">#</th>
                          {result.columns?.map((col: any) => (
                            <th key={col.key} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                              {col.label}
                              {col.required && <span className="text-red-500 ml-0.5">*</span>}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {result.preview?.map((row: any) => (
                          <tr key={row.row}>
                            <td className="px-3 py-2 text-gray-500">{row.row}</td>
                            {result.columns?.map((col: any) => (
                              <td key={col.key} className="px-3 py-2 text-gray-700">
                                {row.data[col.key] || <span className="text-gray-300">-</span>}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {!result.dryRun && (
                <div className={`rounded-lg p-4 flex items-center gap-3 ${
                  result.errors?.length ? 'bg-amber-50 border border-amber-200' : 'bg-emerald-50 border border-emerald-200'
                }`}>
                  {result.errors?.length ? (
                    <AlertTriangle className="h-6 w-6 text-amber-600" />
                  ) : (
                    <CheckCircle className="h-6 w-6 text-emerald-600" />
                  )}
                  <div>
                    <p className="font-medium">{result.imported} records imported</p>
                    {result.errors?.length > 0 && (
                      <div className="mt-2 text-sm text-amber-700">
                        <p className="font-medium">{result.errors.length} errors:</p>
                        <ul className="list-disc list-inside">
                          {result.errors.slice(0, 5).map((err: string, i: number) => (
                            <li key={i}>{err}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )}

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
    </div>
  );
}
