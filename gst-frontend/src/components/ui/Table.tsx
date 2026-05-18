import { ChevronUp, ChevronDown, ChevronsUpDown, Loader2 } from 'lucide-react';

export interface Column<T> {
  key: string;
  header: string;
  render: (item: T) => React.ReactNode;
  sortable?: boolean;
  hideOnMobile?: boolean;
  className?: string;
}

interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (item: T) => string | number;
  loading?: boolean;
  emptyMessage?: string;
  sortKey?: string;
  sortDir?: 'asc' | 'desc';
  onSort?: (key: string) => void;
  onRowClick?: (item: T) => void;
}

export function Table<T>({
  columns,
  data,
  keyExtractor,
  loading,
  emptyMessage = 'No data found',
  sortKey,
  sortDir,
  onSort,
  onRowClick,
}: TableProps<T>) {
  if (loading) {
    return (
      <div className="table-container">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        </div>
      </div>
    );
  }

  if (!data.length) {
    return (
      <div className="table-container">
        <div className="flex flex-col items-center justify-center py-12 text-gray-500">
          <p className="text-sm">{emptyMessage}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="table-container">
      <table className="table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={`${col.sortable ? 'cursor-pointer select-none hover:bg-gray-100' : ''} ${col.className || ''} ${col.hideOnMobile ? 'hidden lg:table-cell' : ''}`}
                onClick={() => col.sortable && onSort?.(col.key)}
              >
                <div className="flex items-center gap-1">
                  {col.header}
                  {col.sortable && (
                    <span className="text-gray-400">
                      {sortKey === col.key ? (
                        sortDir === 'asc' ? (
                          <ChevronUp className="h-3 w-3" />
                        ) : (
                          <ChevronDown className="h-3 w-3" />
                        )
                      ) : (
                        <ChevronsUpDown className="h-3 w-3" />
                      )}
                    </span>
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {data.map((item) => (
            <tr
              key={keyExtractor(item)}
              onClick={() => onRowClick?.(item)}
              className={onRowClick ? 'cursor-pointer' : ''}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`${col.hideOnMobile ? 'hidden lg:table-cell' : ''} ${col.className || ''}`}
                >
                  {col.render(item)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function MobileCards<T>({
  columns,
  data,
  keyExtractor,
  onRowClick,
}: {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (item: T) => string | number;
  onRowClick?: (item: T) => void;
}) {
  return (
    <div className="space-y-3 lg:hidden">
      {data.map((item) => (
        <div
          key={keyExtractor(item)}
          className="card p-4 space-y-2"
          onClick={() => onRowClick?.(item)}
          role={onRowClick ? 'button' : undefined}
        >
          {columns
            .filter((col) => !col.hideOnMobile)
            .map((col) => (
              <div key={col.key} className="flex items-center justify-between gap-4">
                <span className="text-xs font-medium text-gray-500 uppercase">
                  {col.header}
                </span>
                <span className="text-sm text-gray-900 text-right">
                  {col.render(item)}
                </span>
              </div>
            ))}
        </div>
      ))}
    </div>
  );
}