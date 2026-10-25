import { NextResponse } from "next/server";

const apiUrl = process.env.NEXT_PUBLIC_API_URL;
const operatorToken = process.env.OPERATOR_API_TOKEN;

export async function POST() {
  if (!apiUrl || !operatorToken) {
    return NextResponse.json({ detail: "Production operator integration is not configured." }, { status: 503 });
  }
  try {
    const response = await fetch(`${apiUrl}/trigger-crisis`, {
      method: "POST",
      headers: { "X-Operator-Token": operatorToken },
      cache: "no-store"
    });
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Backend control plane is unavailable." }, { status: 502 });
  }
}
