import { getServerSession } from 'next-auth';
import { NextRequest, NextResponse } from 'next/server';
import { authOptions } from '@/utils/auth';
import { BagistoSession } from '@/types/types';

export async function GET(request: NextRequest) {
  const id=request.nextUrl.searchParams.get('id')||'';
  if (!/^\d+$/.test(id)) return NextResponse.json({message:'Invalid download identity'},{status:422});
  const session=await getServerSession(authOptions) as BagistoSession|null;
  if (!session?.user?.accessToken) return NextResponse.json({message:'Sign in to download this purchase'},{status:401});
  const key=process.env.BAGISTO_STOREFRONT_KEY;
  const origin=process.env.NEXT_PUBLIC_BAGISTO_ENDPOINT;
  if (!key||!origin) return NextResponse.json({message:'Store download service is not configured'},{status:503});
  // Only this fixed upstream route is available. The browser never receives
  // the storefront credential or supplies an arbitrary proxy destination.
  const response=await fetch(`${origin.replace(/\/$/,'')}/api/shop/customer-downloadable-products/${id}/download`,{
    cache:'no-store',redirect:'manual',headers:{'Authorization':`Bearer ${session.user.accessToken}`,
      'X-STOREFRONT-KEY':key,'X-Channel':process.env.BAGISTO_CHANNEL||'default','X-Currency':'INR'}
  });
  if (!response.ok) return NextResponse.json({message:'The purchase download is unavailable'}, {status:[401,403,404,429].includes(response.status)?response.status:502});
  return new NextResponse(response.body,{headers:{'Content-Type':response.headers.get('content-type')||'application/octet-stream',
    'Content-Disposition':response.headers.get('content-disposition')||'attachment','Cache-Control':'private, no-store'}});
}
