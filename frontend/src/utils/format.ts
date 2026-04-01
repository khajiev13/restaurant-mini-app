import i18n from '../i18n';

export function formatPrice(amount: number, language: string = i18n.language): string {
  const currencyKey = `common.currency_${language}`;
  const currency = i18n.t(currencyKey);
  
  // Format based on language
  let formatted: string;
  if (language === 'ru') {
    // Russian: 15 000 сум (space as thousand separator)
    formatted = new Intl.NumberFormat('ru-RU').format(amount);
  } else if (language === 'uz') {
    // Uzbek: 15,000 so'm
    formatted = new Intl.NumberFormat('uz-UZ').format(amount);
  } else {
    // English: 15,000 UZS
    formatted = new Intl.NumberFormat('en-US').format(amount);
  }
  
  return `${formatted} ${currency}`;
}

export function formatDate(date: Date | string, language: string = i18n.language): string {
  const dateObj = typeof date === 'string' ? new Date(date) : date;
  
  const localeMap: Record<string, string> = {
    uz: 'uz-UZ',
    ru: 'ru-RU',
    en: 'en-US',
  };
  
  const locale = localeMap[language] || 'en-US';
  
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(dateObj);
}

export function formatDateTime(date: Date | string, language: string = i18n.language): string {
  const dateObj = typeof date === 'string' ? new Date(date) : date;
  
  const localeMap: Record<string, string> = {
    uz: 'uz-UZ',
    ru: 'ru-RU',
    en: 'en-US',
  };
  
  const locale = localeMap[language] || 'en-US';
  
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(dateObj);
}
