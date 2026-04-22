import createMiddleware from 'next-intl/middleware';
import {locales} from './i18n';

export default createMiddleware({
  locales: locales,
  defaultLocale: 'en'
});

export const config = {
  matcher: ['/', '/(en|pt|es|zh)/:path*', '/dashboard/:path*', '/pricing/:path*']
};
