import { type CSSProperties, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { reverseGeocode, suggestAddress } from '../../services/api';
import type { AddressSuggestion } from '../../types/api';
import { loadYmaps3, type YMapInstance } from '../../utils/loadYmaps3';
import { TASHKENT_CENTER, useLocationManager, type MapCoordinates } from '../../hooks/useLocationManager';
import { COLORS, FONTS, Icon } from './ArtisanLayout';

interface MapPickerOverlayProps {
  isOpen: boolean;
  initialLat?: number | null;
  initialLng?: number | null;
  onConfirm: (lat: number, lng: number, address: string) => void;
  onClose: () => void;
}

const OVERLAY_Z_INDEX = 999;
const DEFAULT_ZOOM = 16;

function CenterPin() {
  return (
    <div
      style={{
        position: 'absolute',
        inset: '50% auto auto 50%',
        transform: 'translate(-50%, -100%)',
        pointerEvents: 'none',
        zIndex: 3,
        filter: 'drop-shadow(0 12px 20px rgba(67, 18, 0, 0.22))',
      }}
    >
      <svg width="52" height="62" viewBox="0 0 52 62" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M26 61C26 61 45 40.56 45 26C45 15.5066 36.4934 7 26 7C15.5066 7 7 15.5066 7 26C7 40.56 26 61 26 61Z" fill={COLORS.primary} />
        <circle cx="26" cy="26" r="10" fill={COLORS.onPrimary} />
        <circle cx="26" cy="26" r="4" fill={COLORS.primaryContainer} />
        <ellipse cx="26" cy="6" rx="14" ry="6" fill="rgba(255, 121, 65, 0.22)" />
      </svg>
    </div>
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        background: 'linear-gradient(180deg, rgba(246,246,246,0.96), rgba(255,255,255,0.86))',
        zIndex: 4,
      }}
    >
      <div
        style={{
          width: 34,
          height: 34,
          borderRadius: '50%',
          border: `3px solid ${COLORS.surfaceContainer}`,
          borderTopColor: COLORS.primary,
          animation: 'mapPickerSpin 0.8s linear infinite',
        }}
      />
      <span style={{ color: COLORS.secondary, fontFamily: FONTS.body, fontSize: 14 }}>
        {label}
      </span>
    </div>
  );
}

function formatSuggestionLabel(suggestion: AddressSuggestion): string {
  return suggestion.subtitle
    ? `${suggestion.title}, ${suggestion.subtitle}`
    : suggestion.title;
}

function getSuggestionAddress(suggestion: AddressSuggestion): string {
  return suggestion.address || formatSuggestionLabel(suggestion);
}

function getInitialCenter(
  initialLat: number | null | undefined,
  initialLng: number | null | undefined,
  fallbackCenter: MapCoordinates,
): MapCoordinates {
  if (initialLat !== null && initialLat !== undefined && initialLng !== null && initialLng !== undefined) {
    return { lat: initialLat, lng: initialLng };
  }

  return fallbackCenter;
}

export default function MapPickerOverlay({
  isOpen,
  initialLat,
  initialLng,
  onConfirm,
  onClose,
}: MapPickerOverlayProps) {
  const { t, i18n } = useTranslation();
  const { initialCenter, isResolvingInitialLocation, getCurrentLocation } = useLocationManager();

  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const mapRef = useRef<YMapInstance | null>(null);
  const mapListenerRef = useRef<unknown>(null);
  const centerRef = useRef<MapCoordinates | null>(null);
  const reverseTimerRef = useRef<number | null>(null);
  const reverseRequestIdRef = useRef(0);
  const searchRequestIdRef = useRef(0);

  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [resolvedAddress, setResolvedAddress] = useState('');
  const [nearbySuggestions, setNearbySuggestions] = useState<AddressSuggestion[]>([]);
  const [isResolvingAddress, setIsResolvingAddress] = useState(false);

  const initialCoordinatesProvided = initialLat !== null && initialLat !== undefined
    && initialLng !== null && initialLng !== undefined;
  const canInitializeMap = initialCoordinatesProvided || !isResolvingInitialLocation;

  function clearReverseTimer() {
    if (reverseTimerRef.current !== null) {
      window.clearTimeout(reverseTimerRef.current);
      reverseTimerRef.current = null;
    }
  }

  async function resolveAddressForCenter(lat: number, lng: number): Promise<void> {
    const requestId = reverseRequestIdRef.current + 1;
    reverseRequestIdRef.current = requestId;
    setIsResolvingAddress(true);

    try {
      const response = await reverseGeocode(lat, lng, i18n.language);
      if (reverseRequestIdRef.current !== requestId) {
        return;
      }

      const payload = response.data.data;
      const nextAddress = payload.address
        || [payload.name, payload.description].filter(Boolean).join(', ');
      setResolvedAddress(nextAddress);
      setNearbySuggestions(payload.nearby ?? []);
    } catch {
      if (reverseRequestIdRef.current === requestId && !resolvedAddress) {
        setResolvedAddress('');
        setNearbySuggestions([]);
      }
    } finally {
      if (reverseRequestIdRef.current === requestId) {
        setIsResolvingAddress(false);
      }
    }
  }

  function scheduleReverseGeocode(lat: number, lng: number) {
    clearReverseTimer();
    reverseTimerRef.current = window.setTimeout(() => {
      void resolveAddressForCenter(lat, lng);
    }, 500);
  }

  useEffect(() => {
    if (!isOpen) {
      setMapReady(false);
      setMapError('');
      setSearchQuery('');
      setShowSuggestions(false);
      setSuggestions([]);
      setResolvedAddress('');
      setNearbySuggestions([]);
      setIsSearching(false);
      setIsResolvingAddress(false);
      centerRef.current = null;
      clearReverseTimer();
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !canInitializeMap || !mapContainerRef.current) {
      return;
    }

    let isCancelled = false;
    const startingCenter = getInitialCenter(initialLat, initialLng, initialCenter);

    centerRef.current = startingCenter;
    setResolvedAddress('');
    setMapReady(false);
    setMapError('');

    void loadYmaps3()
      .then(async (ymaps3) => {
        if (isCancelled || !mapContainerRef.current) {
          return;
        }

        const map = new ymaps3.YMap(mapContainerRef.current, {
          location: {
            center: [startingCenter.lng, startingCenter.lat],
            zoom: DEFAULT_ZOOM,
          },
          behaviors: ['drag', 'pinchZoom', 'scrollZoom', 'dblClick'],
        });

        map.addChild(new ymaps3.YMapDefaultSchemeLayer());
        map.addChild(new ymaps3.YMapDefaultFeaturesLayer());

        const listener = new ymaps3.YMapListener({
          onUpdate: ({ location }) => {
            const [lng, lat] = location.center;
            centerRef.current = { lat, lng };
            scheduleReverseGeocode(lat, lng);
          },
        });

        map.addChild(listener);

        mapRef.current = map;
        mapListenerRef.current = listener;
        setMapReady(true);

        await resolveAddressForCenter(startingCenter.lat, startingCenter.lng);
      })
      .catch((error) => {
        if (!isCancelled) {
          console.error('Failed to initialize Yandex map picker', error);
          setMapError(t('checkout.map_unavailable'));
          void resolveAddressForCenter(startingCenter.lat, startingCenter.lng);
        }
      });

    return () => {
      isCancelled = true;
      clearReverseTimer();

      if (mapRef.current) {
        mapRef.current.destroy();
        mapRef.current = null;
      }

      mapListenerRef.current = null;
    };
  }, [canInitializeMap, initialCenter, initialLat, initialLng, isOpen, t]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const query = searchQuery.trim();
    if (!query) {
      searchRequestIdRef.current += 1;
      setSuggestions([]);
      setIsSearching(false);
      return;
    }

    const timeoutId = window.setTimeout(() => {
      const requestId = searchRequestIdRef.current + 1;
      searchRequestIdRef.current = requestId;
      setIsSearching(true);

      const biasCenter = centerRef.current ?? initialCenter ?? TASHKENT_CENTER;

      void suggestAddress(query, i18n.language, biasCenter.lat, biasCenter.lng)
        .then((response) => {
          if (searchRequestIdRef.current !== requestId) {
            return;
          }

          setSuggestions(response.data.data ?? []);
        })
        .catch(() => {
          if (searchRequestIdRef.current === requestId) {
            setSuggestions([]);
          }
        })
        .finally(() => {
          if (searchRequestIdRef.current === requestId) {
            setIsSearching(false);
          }
        });
    }, 300);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [i18n.language, initialCenter, isOpen, searchQuery]);

  async function handleUseCurrentLocation(): Promise<void> {
    const location = await getCurrentLocation();
    centerRef.current = location;

    if (mapRef.current) {
      mapRef.current.setLocation({
        center: [location.lng, location.lat],
        zoom: DEFAULT_ZOOM,
        duration: 300,
      });
    }

    void resolveAddressForCenter(location.lat, location.lng);
  }

  function dismissKeyboard() {
    searchInputRef.current?.blur();
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
  }

  function applySuggestionSelection(suggestion: AddressSuggestion, shouldDismissKeyboard = false) {
    const nextAddress = getSuggestionAddress(suggestion);
    setSearchQuery(nextAddress);
    setResolvedAddress(nextAddress);
    setSuggestions([]);
    setShowSuggestions(false);
    setNearbySuggestions((current) => {
      const deduped = current.filter((item) => getSuggestionAddress(item) !== nextAddress);
      return [suggestion, ...deduped];
    });

    centerRef.current = { lat: suggestion.lat, lng: suggestion.lng };

    if (mapRef.current) {
      mapRef.current.setLocation({
        center: [suggestion.lng, suggestion.lat],
        zoom: DEFAULT_ZOOM,
        duration: 300,
      });
    }

    if (shouldDismissKeyboard) {
      dismissKeyboard();
    }

    void resolveAddressForCenter(suggestion.lat, suggestion.lng);
  }

  function handleSelectSuggestion(suggestion: AddressSuggestion) {
    applySuggestionSelection(suggestion, true);
  }

  const currentCenter = centerRef.current;
  const confirmAddress = resolvedAddress || searchQuery.trim();
  const showInitialLoader = !initialCoordinatesProvided && isResolvingInitialLocation;
  const hasSearchQuery = searchQuery.trim().length > 0;
  const shouldShowSuggestions = (showSuggestions || isSearching) && (hasSearchQuery || isSearching);
  const nearbySuggestionOptions = nearbySuggestions
    .filter((suggestion) => getSuggestionAddress(suggestion) !== confirmAddress)
    .slice(0, 3);
  const gpsButtonBottom = nearbySuggestionOptions.length > 0 ? 228 : 148;

  if (!isOpen) {
    return null;
  }

  const shellStyle: CSSProperties = {
    position: 'fixed',
    inset: 0,
    zIndex: OVERLAY_Z_INDEX,
    display: 'flex',
    flexDirection: 'column',
    background: COLORS.surface,
    animation: 'mapPickerSlideUp 0.28s ease-out',
  };

  return (
    <div style={shellStyle}>
      <style>
        {`
          @keyframes mapPickerSlideUp {
            from { opacity: 0; transform: translateY(24px); }
            to { opacity: 1; transform: translateY(0); }
          }

          @keyframes mapPickerSpin {
            to { transform: rotate(360deg); }
          }
        `}
      </style>

      <div
        style={{
          position: 'relative',
          zIndex: 8,
          overflow: 'visible',
          paddingTop: 'calc(env(safe-area-inset-top, 0px) + 12px)',
          paddingLeft: 16,
          paddingRight: 16,
          paddingBottom: 12,
          background: 'rgba(250, 250, 249, 0.94)',
          backdropFilter: 'blur(16px)',
          borderBottom: '1px solid rgba(172,173,173,0.18)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <button
            onClick={onClose}
            type="button"
            style={{
              width: 42,
              height: 42,
              borderRadius: '50%',
              border: 'none',
              background: COLORS.surfaceContainerLow,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
            }}
          >
            <Icon name="chevron_left" style={{ color: COLORS.onSurface }} />
          </button>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontFamily: FONTS.headline, fontSize: 18, fontWeight: 700, color: COLORS.onSurface }}>
              {t('checkout.map_title')}
            </span>
            <span style={{ fontFamily: FONTS.body, fontSize: 12, color: COLORS.secondary }}>
              {t('checkout.map_drag_hint')}
            </span>
          </div>
        </div>

        <div style={{ position: 'relative' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              background: COLORS.surfaceContainerLowest,
              borderRadius: 16,
              padding: '0 14px',
              height: 52,
              boxShadow: '0 8px 24px rgba(45,47,47,0.06)',
            }}
          >
            <Icon name="search" size={20} style={{ color: COLORS.outline }} />
            <input
              autoFocus
              ref={searchInputRef}
              value={searchQuery}
              onChange={(event) => {
                setSearchQuery(event.target.value);
                setShowSuggestions(true);
              }}
              onFocus={() => setShowSuggestions(true)}
              onBlur={() => window.setTimeout(() => {
                if (!searchQuery.trim()) {
                  setShowSuggestions(false);
                }
              }, 120)}
              placeholder={t('checkout.map_search_placeholder')}
              style={{
                width: '100%',
                border: 'none',
                background: 'transparent',
                outline: 'none',
                color: COLORS.onSurface,
                fontSize: 15,
                fontFamily: FONTS.body,
              }}
            />
          </div>

          {shouldShowSuggestions && (
            <div
              style={{
                position: 'absolute',
                top: 58,
                left: 0,
                right: 0,
                maxHeight: 260,
                overflowY: 'auto',
                background: COLORS.surfaceContainerLowest,
                borderRadius: 16,
                boxShadow: '0 16px 40px rgba(45,47,47,0.14)',
                border: '1px solid rgba(172,173,173,0.18)',
                zIndex: 6,
              }}
            >
              {isSearching && (
                <div style={{ padding: '14px 16px', fontSize: 14, color: COLORS.secondary, fontFamily: FONTS.body }}>
                  {t('common.loading', 'Loading...')}
                </div>
              )}

              {!isSearching && suggestions.map((suggestion) => {
                const label = formatSuggestionLabel(suggestion);

                return (
                  <button
                    key={`${suggestion.lat}-${suggestion.lng}-${label}`}
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => handleSelectSuggestion(suggestion)}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 12,
                      textAlign: 'left',
                      background: 'transparent',
                      border: 'none',
                      borderBottom: '1px solid rgba(172,173,173,0.12)',
                      padding: '14px 16px',
                      cursor: 'pointer',
                    }}
                  >
                    <Icon name="location_on" fill size={18} style={{ color: COLORS.primary, marginTop: 1 }} />
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <span style={{ fontFamily: FONTS.body, fontSize: 14, fontWeight: 700, color: COLORS.onSurface }}>
                        {suggestion.title}
                      </span>
                      {suggestion.subtitle && (
                        <span style={{ fontFamily: FONTS.body, fontSize: 12, color: COLORS.secondary }}>
                          {suggestion.subtitle}
                        </span>
                      )}
                    </span>
                  </button>
                );
              })}

              {!isSearching && hasSearchQuery && suggestions.length === 0 && (
                <div
                  style={{
                    padding: '14px 16px',
                    fontSize: 14,
                    color: COLORS.secondary,
                    fontFamily: FONTS.body,
                  }}
                >
                  {t('checkout.map_no_results', 'No results found')}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
        <div ref={mapContainerRef} style={{ position: 'absolute', inset: 0 }} />
        {mapReady && <CenterPin />}

        <button
          type="button"
          onClick={() => void handleUseCurrentLocation()}
          aria-label={t('checkout.map_my_location')}
          title={t('checkout.map_my_location')}
          style={{
            position: 'absolute',
            right: 16,
            bottom: gpsButtonBottom,
            width: 52,
            height: 52,
            borderRadius: '50%',
            border: 'none',
            background: COLORS.surfaceContainerLowest,
            boxShadow: '0 14px 28px rgba(45,47,47,0.18)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            zIndex: 5,
          }}
        >
          <Icon name="my_location" fill size={22} style={{ color: COLORS.primary }} />
        </button>

        {(showInitialLoader || (!mapReady && !mapError)) && (
          <LoadingState label={t('common.loading', 'Loading...')} />
        )}

        {mapError && (
          <div
            style={{
              position: 'absolute',
              left: 16,
              right: 16,
              top: 16,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '12px 14px',
              background: 'rgba(179, 27, 37, 0.92)',
              borderRadius: 16,
              color: '#fff',
              fontFamily: FONTS.body,
              zIndex: 6,
              boxShadow: '0 14px 30px rgba(179,27,37,0.22)',
            }}
          >
            <Icon name="warning" fill size={18} style={{ color: '#fff', flexShrink: 0 }} />
            <span style={{ fontSize: 13, lineHeight: 1.45 }}>
              {mapError}
            </span>
          </div>
        )}

        <div
          style={{
            position: 'absolute',
            left: 16,
            right: 16,
            bottom: 16,
            padding: 16,
            borderRadius: 22,
            background: 'rgba(255,255,255,0.96)',
            backdropFilter: 'blur(16px)',
            boxShadow: '0 16px 48px rgba(45,47,47,0.18)',
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
            zIndex: 4,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
            <Icon name="place" fill size={20} style={{ color: COLORS.primary, marginTop: 2 }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontFamily: FONTS.body, fontSize: 14, fontWeight: 700, color: COLORS.onSurface }}>
                {isResolvingAddress
                  ? t('checkout.map_loading_address')
                  : confirmAddress || t('checkout.map_drag_hint')}
              </span>
              <span style={{ fontFamily: FONTS.body, fontSize: 12, color: COLORS.secondary }}>
                {t('checkout.map_drag_hint')}
              </span>
            </div>
          </div>

          {nearbySuggestionOptions.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={{ fontFamily: FONTS.body, fontSize: 12, fontWeight: 700, color: COLORS.secondary }}>
                {t('checkout.map_nearby_title')}
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 132, overflowY: 'auto' }}>
                {nearbySuggestionOptions.map((suggestion) => {
                  const label = getSuggestionAddress(suggestion);

                  return (
                    <button
                      key={`${suggestion.lat}-${suggestion.lng}-${label}`}
                      type="button"
                      onClick={() => applySuggestionSelection(suggestion, true)}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        borderRadius: 14,
                        border: '1px solid rgba(172,173,173,0.2)',
                        background: COLORS.surfaceContainerLowest,
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: 10,
                        textAlign: 'left',
                        cursor: 'pointer',
                      }}
                    >
                      <Icon name="near_me" fill size={16} style={{ color: COLORS.primary, marginTop: 2 }} />
                      <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                        <span style={{ fontFamily: FONTS.body, fontSize: 13, fontWeight: 700, color: COLORS.onSurface }}>
                          {suggestion.title}
                        </span>
                        <span style={{ fontFamily: FONTS.body, fontSize: 12, color: COLORS.secondary }}>
                          {suggestion.address || suggestion.subtitle}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={() => {
              if (!currentCenter || !confirmAddress) {
                return;
              }

              onConfirm(currentCenter.lat, currentCenter.lng, confirmAddress);
            }}
            disabled={!currentCenter || !confirmAddress}
            style={{
              width: '100%',
              border: 'none',
              borderRadius: 16,
              padding: '15px 18px',
              background: !currentCenter || !confirmAddress
                ? COLORS.surfaceContainerHigh
                : 'linear-gradient(135deg, #a33800 0%, #ff7941 100%)',
              color: !currentCenter || !confirmAddress ? COLORS.secondary : COLORS.onPrimary,
              fontFamily: FONTS.headline,
              fontSize: 16,
              fontWeight: 700,
              cursor: !currentCenter || !confirmAddress ? 'not-allowed' : 'pointer',
            }}
          >
            {t('checkout.map_confirm')}
          </button>
        </div>
      </div>
    </div>
  );
}
