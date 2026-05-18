import { useParams, useNavigate } from 'react-router-dom';
import { useParty } from '@/lib/hooks';
import { PageHeader } from '@/components/ui/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { Button } from '@/components/ui/Button';
import { formatCurrency, formatDate, formatGstin, formatPan, formatPhone } from '@/utils/format';
import { ArrowLeft, Edit, Phone, Mail, MapPin, DollarSign } from 'lucide-react';

export function PartyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: party, isLoading, error, refetch } = useParty(id || '');

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="card p-6 space-y-4">
          <Skeleton className="h-6 w-64" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-4 w-48" />
        </div>
      </div>
    );
  }

  if (error || !party) {
    return <ErrorState onRetry={refetch} message="Failed to load party details" />;
  }

  const address = party.addresses?.[0];

  return (
    <div className="space-y-6">
      <PageHeader
        title={party.party_name}
        subtitle={`${party.party_type} Details`}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => navigate(-1)}>
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
            <Button onClick={() => navigate(`/parties?type=${party.party_type}`)}>
              <Edit className="h-4 w-4" />
              Edit
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <div className="card">
            <div className="card-header">
              <h3 className="font-semibold text-gray-900">Party Information</h3>
            </div>
            <div className="card-body space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">GSTIN</p>
                  <p className="text-sm font-mono font-medium text-gray-900">{formatGstin(party.gstin)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">PAN</p>
                  <p className="text-sm font-mono font-medium text-gray-900">{formatPan(party.pan)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">Type</p>
                  <Badge variant="info">{party.party_type}</Badge>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">Status</p>
                  <Badge variant={party.is_deleted ? 'default' : 'success'}>
                    {party.is_deleted ? 'Inactive' : 'Active'}
                  </Badge>
                </div>
              </div>
            </div>
          </div>

          <div className="card mt-6">
            <div className="card-header">
              <h3 className="font-semibold text-gray-900">Financial Details</h3>
            </div>
            <div className="card-body grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider">Opening Balance</p>
                <p className="text-lg font-semibold text-gray-900">{formatCurrency(party.opening_balance)}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider">Credit Limit</p>
                <p className="text-lg font-semibold text-gray-900">{formatCurrency(party.credit_limit)}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider">Credit Days</p>
                <p className="text-lg font-semibold text-gray-900">{party.credit_days || 0}d</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider">TDS</p>
                <Badge variant={party.tds_applicable ? 'warning' : 'neutral'}>
                  {party.tds_applicable ? 'Applicable' : 'N/A'}
                </Badge>
              </div>
            </div>
          </div>
        </div>

        <div>
          <div className="card">
            <div className="card-header">
              <h3 className="font-semibold text-gray-900">Contacts</h3>
            </div>
            <div className="divide-y divide-gray-100">
              {party.contacts?.map((c, i) => (
                <div key={i} className="px-6 py-3 space-y-1">
                  <p className="text-sm font-medium text-gray-900">{c.name}</p>
                  {c.phone && (
                    <p className="text-sm text-gray-600 flex items-center gap-1">
                      <Phone className="h-3 w-3" /> {formatPhone(c.phone)}
                    </p>
                  )}
                  {c.email && (
                    <p className="text-sm text-gray-600 flex items-center gap-1">
                      <Mail className="h-3 w-3" /> {c.email}
                    </p>
                  )}
                </div>
              ))}
              {(!party.contacts || party.contacts.length === 0) && (
                <div className="px-6 py-4 text-sm text-gray-500">No contacts listed</div>
              )}
            </div>
          </div>

          {address && (
            <div className="card mt-4">
              <div className="card-header">
                <h3 className="font-semibold text-gray-900">Address</h3>
              </div>
              <div className="card-body space-y-1">
                <p className="text-sm text-gray-600 flex items-start gap-1">
                  <MapPin className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>
                    {address.line1}
                    {address.city && <>, {address.city}</>}
                  </span>
                </p>
                <p className="text-sm text-gray-600">{address.pincode}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}