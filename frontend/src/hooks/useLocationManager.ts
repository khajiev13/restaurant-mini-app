import { useEffect, useState } from 'react';
import type { TelegramLocation, TelegramLocationManager } from '../types/telegram';

export interface MapCoordinates {
  lat: number;
  lng: number;
}

export const TASHKENT_CENTER: MapCoordinates = {
  lat: 41.2995,
  lng: 69.2401,
};

const LOCATION_TIMEOUT_MS = 4000;

function getLocationManager(): TelegramLocationManager | undefined {
  return window.Telegram?.WebApp?.LocationManager;
}

function initLocationManager(manager: TelegramLocationManager): Promise<void> {
  return new Promise((resolve) => {
    if (manager.isInited) {
      resolve();
      return;
    }

    manager.init(() => resolve());
  });
}

function getLocation(manager: TelegramLocationManager): Promise<TelegramLocation | null> {
  return new Promise((resolve) => {
    const timeoutId = window.setTimeout(() => resolve(null), LOCATION_TIMEOUT_MS);

    manager.getLocation((location) => {
      window.clearTimeout(timeoutId);
      resolve(location);
    });
  });
}

export async function getTelegramLocation(): Promise<MapCoordinates> {
  const manager = getLocationManager();
  if (!manager) {
    return TASHKENT_CENTER;
  }

  try {
    await initLocationManager(manager);
    if (!manager.isLocationAvailable) {
      return TASHKENT_CENTER;
    }

    const location = await getLocation(manager);
    if (!location) {
      return TASHKENT_CENTER;
    }

    return {
      lat: location.latitude,
      lng: location.longitude,
    };
  } catch {
    return TASHKENT_CENTER;
  }
}

export function useLocationManager(): {
  initialCenter: MapCoordinates;
  isResolvingInitialLocation: boolean;
  getCurrentLocation: () => Promise<MapCoordinates>;
} {
  const [initialCenter, setInitialCenter] = useState<MapCoordinates>(TASHKENT_CENTER);
  const [isResolvingInitialLocation, setIsResolvingInitialLocation] = useState(true);

  useEffect(() => {
    let isActive = true;

    void getTelegramLocation()
      .then((location) => {
        if (isActive) {
          setInitialCenter(location);
        }
      })
      .finally(() => {
        if (isActive) {
          setIsResolvingInitialLocation(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, []);

  return {
    initialCenter,
    isResolvingInitialLocation,
    getCurrentLocation: getTelegramLocation,
  };
}
