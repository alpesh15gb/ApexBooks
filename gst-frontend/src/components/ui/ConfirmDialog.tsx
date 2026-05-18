import { AlertTriangle } from 'lucide-react';
import { Button } from './Button';

interface ConfirmDialogProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
  variant?: 'danger' | 'warning';
  loading?: boolean;
}

export function ConfirmDialog({
  isOpen,
  onConfirm,
  onCancel,
  title,
  message,
  confirmLabel = 'Confirm',
  variant = 'danger',
  loading,
}: ConfirmDialogProps) {
  if (!isOpen) return null;

  return (
    <>
      <div className="modal-backdrop" onClick={onCancel} />
      <div className="modal-content">
        <div className="modal-panel max-w-sm">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <div
                className={`p-2 rounded-full ${
                  variant === 'danger' ? 'bg-red-100' : 'bg-amber-100'
                }`}
              >
                <AlertTriangle
                  className={`h-5 w-5 ${
                    variant === 'danger' ? 'text-red-600' : 'text-amber-600'
                  }`}
                />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
              </div>
            </div>
            <p className="text-sm text-gray-600 mb-6">{message}</p>
            <div className="flex justify-end gap-3">
              <Button variant="secondary" onClick={onCancel}>
                Cancel
              </Button>
              <Button
                variant={variant === 'danger' ? 'danger' : 'primary'}
                onClick={onConfirm}
                loading={loading}
              >
                {confirmLabel}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}