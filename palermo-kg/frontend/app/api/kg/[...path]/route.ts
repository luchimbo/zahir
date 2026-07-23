import { NextRequest, NextResponse } from "next/server";

const KG_API_BASE = process.env.KG_API_BASE ?? "http://127.0.0.1:8000";
const KG_API_KEY = process.env.KG_API_KEY;

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path: pathParts } = await params;
  const path = pathParts.join("/");
  const upstream = new URL(`/api/${path}`, KG_API_BASE);
  upstream.search = request.nextUrl.search;

  try {
    const response = await fetch(upstream, {
      headers: { accept: "application/json", ...(KG_API_KEY ? { "x-api-key": KG_API_KEY } : {}) },
      cache: "no-store"
    });

    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json"
      }
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "kg_api_unreachable",
        detail: error instanceof Error ? error.message : "Unknown error"
      },
      { status: 502 }
    );
  }
}
