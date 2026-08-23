import {NextResponse} from 'next/server';import type {NextRequest} from 'next/server';
export function middleware(req:NextRequest){if(!req.cookies.get('ld_session')){const u=new URL('/login',req.url);u.searchParams.set('returnTo','/app/dashboard');return NextResponse.redirect(u)}return NextResponse.next()}
export const config={matcher:['/dashboard/:path*','/imovel-360/:path*','/re-rural/:path*','/condominio/:path*','/energia-solar/:path*','/ai-tec/:path*','/prefeitura/:path*']};
