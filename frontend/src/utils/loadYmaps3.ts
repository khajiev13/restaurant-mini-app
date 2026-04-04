export interface YMapLocationRequest {
  center?: [number, number];
  zoom?: number;
  duration?: number;
}

interface YMapLocation {
  center: [number, number];
  zoom: number;
}

interface YMapUpdateEvent {
  type: 'update';
  location: YMapLocation;
  mapInAction: boolean;
}

export interface YMapInstance {
  addChild(child: unknown): YMapInstance;
  removeChild(child: unknown): YMapInstance;
  setLocation(location: YMapLocationRequest): void;
  destroy(): void;
}

export interface YMaps3Api {
  ready: Promise<void>;
  YMap: new (
    root: HTMLElement,
    props: { location: YMapLocationRequest; behaviors?: string[] },
  ) => YMapInstance;
  YMapDefaultSchemeLayer: new () => unknown;
  YMapDefaultFeaturesLayer: new () => unknown;
  YMapListener: new (props: { onUpdate?: (event: YMapUpdateEvent) => void }) => unknown;
}

declare global {
  interface Window {
    ymaps3?: YMaps3Api;
  }
}

const SCRIPT_ID = 'yandex-maps-v3-script';
const MAPS_LANG = 'ru_RU';

let ymaps3Promise: Promise<YMaps3Api> | null = null;

function resolveYmaps3(
  resolve: (value: YMaps3Api) => void,
  reject: (reason?: unknown) => void,
): void {
  const api = window.ymaps3;
  if (!api) {
    ymaps3Promise = null;
    reject(new Error('Yandex Maps API did not initialize.'));
    return;
  }

  void api.ready
    .then(() => resolve(api))
    .catch((error) => {
      ymaps3Promise = null;
      reject(error);
    });
}

export function loadYmaps3(): Promise<YMaps3Api> {
  const apiKey = import.meta.env.VITE_YANDEX_MAPS_API_KEY;
  if (!apiKey) {
    return Promise.reject(new Error('VITE_YANDEX_MAPS_API_KEY is not configured.'));
  }

  if (window.ymaps3) {
    return window.ymaps3.ready.then(() => window.ymaps3 as YMaps3Api);
  }

  if (ymaps3Promise) {
    return ymaps3Promise;
  }

  ymaps3Promise = new Promise<YMaps3Api>((resolve, reject) => {
    const existingScript = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;

    if (existingScript) {
      existingScript.addEventListener('load', () => resolveYmaps3(resolve, reject), { once: true });
      existingScript.addEventListener(
        'error',
        () => {
          ymaps3Promise = null;
          reject(new Error('Failed to load Yandex Maps API.'));
        },
        { once: true },
      );
      return;
    }

    const script = document.createElement('script');
    script.id = SCRIPT_ID;
    script.async = true;
    script.src = `https://api-maps.yandex.ru/v3/?apikey=${encodeURIComponent(apiKey)}&lang=${MAPS_LANG}`;
    script.onload = () => resolveYmaps3(resolve, reject);
    script.onerror = () => {
      ymaps3Promise = null;
      reject(new Error('Failed to load Yandex Maps API.'));
    };
    document.head.appendChild(script);
  });

  return ymaps3Promise;
}
