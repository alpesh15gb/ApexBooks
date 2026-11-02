import { createHash, createHmac, timingSafeEqual } from 'node:crypto';
import { revalidatePath, revalidateTag } from 'next/cache';
import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  const secret = process.env.APEX_STOREFRONT_WEBHOOK_SECRET;
  const connection = process.env.APEX_CONNECTION_ID;
  const channel = process.env.BAGISTO_CHANNEL;
  if (!secret || !connection || !channel) return NextResponse.json({error:'Store integration is not configured'}, {status:503});
  const stamp = request.headers.get('x-apex-timestamp') || '';
  const provided = request.headers.get('x-apex-signature') || '';
  if (!/^\d+$/.test(stamp) || Math.abs(Date.now()/1000-Number(stamp)) > 300 || !/^[a-f0-9]{64}$/.test(provided)) return NextResponse.json({error:'Invalid signature'}, {status:401});
  const raw = await request.text();
  if (Buffer.byteLength(raw) > 100_000) return NextResponse.json({error:'Request too large'}, {status:413});
  const message = `${stamp}\nPOST\n/api/apex/revalidate\n${createHash('sha256').update(raw).digest('hex')}`;
  const expected = createHmac('sha256',secret).update(message).digest();
  if (!timingSafeEqual(expected,Buffer.from(provided,'hex'))) return NextResponse.json({error:'Invalid signature'}, {status:401});
  let payload: Record<string,unknown>;
  try {
    const parsed: unknown=JSON.parse(raw);
    if (!parsed || typeof parsed!=='object' || Array.isArray(parsed)) throw new Error('Invalid event');
    payload=parsed as Record<string,unknown>;
  }
  catch { return NextResponse.json({error:'Invalid event'}, {status:422}); }
  if (payload.connection_id!==connection || payload.channel!==channel) return NextResponse.json({error:'Event belongs to another storefront'}, {status:403});
  if (payload.resource!=='catalogue') return NextResponse.json({error:'Unsupported cache resource'}, {status:422});
  // This deployment owns one channel. No caller-controlled paths or cache tags.
  revalidateTag('products',{expire:0});
  revalidateTag('categories',{expire:0});
  revalidatePath('/','layout');
  return NextResponse.json({status:'done',event_id:payload.event_id,revalidated:true});
}
