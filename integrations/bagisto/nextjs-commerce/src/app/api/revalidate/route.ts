import { NextResponse } from "next/server";

export async function POST(): Promise<NextResponse> {
  return NextResponse.json({message:'Use the signed /api/apex/revalidate endpoint'}, {status:410});
}
