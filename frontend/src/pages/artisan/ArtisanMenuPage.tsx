import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ArtisanLayout, { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import { getMe } from '../../services/api';
import { useAuthStore } from '../../stores/authStore';
import { useCartStore } from '../../stores/cartStore';
import { useMenuStore } from '../../stores/menuStore';
import { formatPrice } from '../../utils/format';
import type { MenuCategory, MenuItem } from '../../types/api';
import catBaliqlar from '../../assets/categories/baliqlar.jpg';
import catChoy from '../../assets/categories/choy.jpg';
import catOvqat from '../../assets/categories/ovqat.jpg';
import catSomsa from '../../assets/categories/somsa.jpg';
import catSuvlar from '../../assets/categories/suvlar.jpg';

const tg = window.Telegram?.WebApp;
const haptic = tg?.HapticFeedback;

interface GroupedCategory extends MenuCategory {
  products: MenuItem[];
}

const CATEGORY_ICONS: Record<string, string> = {
  main: 'bakery_dining', pizza: 'local_pizza', salad: 'nutrition',
  soup: 'soup_kitchen', drinks: 'local_cafe', desserts: 'icecream',
  beverages: 'local_cafe', bar: 'local_bar', default: 'restaurant',
};

const ZoomedCircleIcon = ({ src, alt, size = 28 }: { src: string, alt: string, size?: number }) => (
  <div style={{
    width: size,
    height: size,
    minWidth: size,
    minHeight: size,
    borderRadius: '50%',
    overflow: 'hidden',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
    flexShrink: 0,
    position: 'relative'
  }}>
    <img src={src} alt={alt} draggable={false} style={{
      position: 'absolute',
      width: '250%',
      height: '250%',
      objectFit: 'cover',
      top: '50%',
      left: '50%',
      transform: 'translate(-50%, -50%)',
      pointerEvents: 'none',
      userSelect: 'none',
      WebkitUserSelect: 'none'
    }} />
  </div>
);

function getCategoryIcon(name: string, isActive?: boolean): React.ReactNode {
  const lower = name.toLowerCase();
  
  if (lower.includes('baliq')) return <ZoomedCircleIcon src={catBaliqlar} alt={name} size={isActive ? 40 : 36} />;
  if (lower.includes('choy') || lower.includes('tea')) return <ZoomedCircleIcon src={catChoy} alt={name} size={isActive ? 40 : 36} />;
  if (lower.includes('ovqat') || lower.includes('food') || lower.includes('main')) return <ZoomedCircleIcon src={catOvqat} alt={name} size={isActive ? 40 : 36} />;
  if (lower.includes('somsa')) return <ZoomedCircleIcon src={catSomsa} alt={name} size={isActive ? 40 : 36} />;
  if (lower.includes('suv') || lower.includes('water')) return <ZoomedCircleIcon src={catSuvlar} alt={name} size={isActive ? 40 : 36} />;

  let iconName = CATEGORY_ICONS.default;
  for (const [key, icon] of Object.entries(CATEGORY_ICONS)) {
    if (lower.includes(key)) {
      iconName = icon;
      break;
    }
  }
  return <Icon name={iconName} fill={isActive} style={{ fontSize: 24 }} />;
}

// --- Product Card ---
function ProductCard({ product, quantity, onAdd, onRemove, language }: {
  product: MenuItem; quantity: number;
  onAdd: () => void; onRemove: () => void; language: string;
}) {
  const imgUrl = product.images?.[0]?.url;

  return (
    <div
      style={{
        backgroundColor: COLORS.surfaceContainerLowest, borderRadius: 12, padding: 12,
        display: 'flex', gap: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
        border: `1px solid rgba(172, 173, 173, 0.05)`,
      }}
    >
      {imgUrl && (
        <img
          src={imgUrl} alt={product.name}
          style={{ width: 96, height: 96, borderRadius: 8, objectFit: 'cover', flexShrink: 0 }}
        />
      )}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '2px 0' }}>
        <div>
          <h3 style={{ fontFamily: FONTS.headline, fontWeight: 700, color: COLORS.onSurface, fontSize: 15, margin: 0 }}>
            {product.name}
          </h3>
          {product.description && (
            <p style={{
              fontFamily: FONTS.body, fontSize: 12, color: COLORS.onSurfaceVariant,
              margin: '4px 0 0', lineHeight: 1.5,
              overflow: 'hidden', textOverflow: 'ellipsis',
              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
            }}>
              {product.description}
            </p>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
          <span style={{ fontFamily: FONTS.headline, fontWeight: 700, color: COLORS.primary, fontSize: 14 }}>
            {formatPrice(product.price, language)}
          </span>
          {quantity > 0 ? (
            <div style={{
              display: 'flex', alignItems: 'center',
              backgroundColor: 'rgba(255, 121, 65, 0.2)',
              borderRadius: 9999, padding: 4,
            }}>
              <button
                onClick={onRemove}
                style={{
                  width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  borderRadius: '50%', backgroundColor: '#fff', color: COLORS.primary,
                  border: 'none', cursor: 'pointer', boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                }}
              >
                <Icon name="remove" size={16} />
              </button>
              <span style={{ padding: '0 12px', fontFamily: FONTS.headline, fontWeight: 700, fontSize: 14, color: COLORS.onPrimaryContainer }}>
                {quantity}
              </span>
              <button
                onClick={onAdd}
                style={{
                  width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  borderRadius: '50%', backgroundColor: COLORS.primary, color: '#fff',
                  border: 'none', cursor: 'pointer', boxShadow: '0 2px 6px rgba(163, 56, 0, 0.3)',
                }}
              >
                <Icon name="add" size={16} />
              </button>
            </div>
          ) : (
            <button
              onClick={onAdd}
              style={{
                width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center',
                borderRadius: '50%', backgroundColor: COLORS.primary, color: '#fff',
                border: 'none', cursor: 'pointer',
                boxShadow: '0 4px 12px rgba(163, 56, 0, 0.25)',
              }}
            >
              <Icon name="add" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ArtisanMenuPage() {
  const { t, i18n } = useTranslation();
  const menu = useMenuStore((s) => s.menu);
  const loading = useMenuStore((s) => s.loading);
  const fetchMenu = useMenuStore((s) => s.fetchMenu);
  const error = useMenuStore((s) => s.error);
  const retry = useMenuStore((s) => s.retry);
  const addItem = useCartStore((s) => s.addItem);
  const removeItem = useCartStore((s) => s.removeItem);
  const updateQuantity = useCartStore((s) => s.updateQuantity);
  const cartItems = useCartStore((s) => s.items);
  const itemCount = useCartStore((s) => s.getItemCount());
  const cartTotal = useCartStore((s) => s.getTotal());
  const navigate = useNavigate();
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const categoryRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const contentSectionRef = useRef<HTMLElement>(null);
  const isScrollingByClick = useRef(false);
  const activeCategoryRef = useRef<string | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | undefined>();
  const [firstName, setFirstName] = useState<string | undefined>();

  const grouped: GroupedCategory[] = useMemo(() => {
    const categories = menu?.categories || [];
    const items = menu?.items || [];

    return categories
      .sort((a, b) => a.sortOrder - b.sortOrder)
      .map((c) => ({ ...c, products: items.filter((i) => i.categoryId === c.id).sort((a, b) => a.sortOrder - b.sortOrder) }))
      .filter((c) => c.products.length > 0);
  }, [menu?.categories, menu?.items]);

  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;
    getMe()
      .then((res) => {
        if (!cancelled) {
          setAvatarUrl(res.data.data?.photo_url || undefined);
          setFirstName(res.data.data?.first_name || undefined);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [isAuthenticated]);

  useEffect(() => { tg?.BackButton?.hide(); }, []);
  useEffect(() => { void fetchMenu(); }, [fetchMenu]);

  // Hide Telegram's MainButton in Artisan theme — we use our own cart bar
  useEffect(() => {
    const mainButton = tg?.MainButton;
    if (!mainButton) return;
    mainButton.setParams({ is_visible: false });
    return () => { mainButton.setParams({ is_visible: false }); };
  }, []);

  // Scroll spy: passive scroll listener on the content section
  useEffect(() => {
    const scrollContainer = contentSectionRef.current;
    if (!scrollContainer || grouped.length === 0) return;

    if (!activeCategoryRef.current) {
      activeCategoryRef.current = grouped[0].id;
      setActiveCategory(grouped[0].id);
    }

    const handleScroll = () => {
      if (isScrollingByClick.current) return;

      const containerTop = scrollContainer.getBoundingClientRect().top;
      let closestId: string | null = null;
      let closestDistance = Infinity;

      for (const cat of grouped) {
        const el = categoryRefs.current[cat.id];
        if (!el) continue;
        const distance = Math.abs(el.getBoundingClientRect().top - containerTop);
        if (distance < closestDistance) {
          closestDistance = distance;
          closestId = cat.id;
        }
      }

      if (closestId && closestId !== activeCategoryRef.current) {
        activeCategoryRef.current = closestId;
        setActiveCategory(closestId);
      }
    };

    scrollContainer.addEventListener('scroll', handleScroll, { passive: true });
    return () => scrollContainer.removeEventListener('scroll', handleScroll);
  }, [grouped]);

  const handleCategoryClick = (id: string) => {
    const ref = categoryRefs.current[id];
    if (ref) {
      isScrollingByClick.current = true;
      activeCategoryRef.current = id;
      setActiveCategory(id);
      ref.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setTimeout(() => { isScrollingByClick.current = false; }, 800);
    }
  };

  const handleAdd = (product: MenuItem) => { addItem(product); haptic?.impactOccurred('light'); };
  const handleRemove = (id: string) => {
    const item = cartItems.find((i) => i.id === id);
    if (item && item.quantity > 1) updateQuantity(id, item.quantity - 1);
    else removeItem(id);
    haptic?.impactOccurred('light');
  };

  const getQuantity = (id: string) => cartItems.find((i) => i.id === id)?.quantity || 0;

  if (loading) {
    return (
      <ArtisanLayout>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 80, minHeight: '80vh' }}>
          <div style={{ width: 32, height: 32, border: `3px solid ${COLORS.surfaceContainer}`, borderTopColor: COLORS.primary, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </ArtisanLayout>
    );
  }

  if (error && !menu) {
    return (
      <ArtisanLayout>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 60, minHeight: '80vh', gap: 16 }}>
          <p style={{ fontSize: 16, color: COLORS.secondary, textAlign: 'center' }}>{error}</p>
          <button onClick={() => void retry()} style={{ background: COLORS.primary, color: '#fff', padding: '10px 24px', borderRadius: 8, border: 'none', fontWeight: 600, cursor: 'pointer' }}>
            {t('menu.retry', 'Retry')}
          </button>
        </div>
      </ArtisanLayout>
    );
  }



  const initial = firstName ? firstName[0].toUpperCase() : undefined;

  return (
    <ArtisanLayout hideBottomNav={itemCount > 0} avatarUrl={avatarUrl} avatarInitial={initial}>
      <div style={{ display: 'flex', height: '100vh', flexDirection: 'column', paddingBottom: itemCount > 0 ? 0 : 80, overflow: 'hidden' }}>
        {/* Body: sidebar + content */}
        <div style={{ display: 'flex', flex: 1, paddingTop: 64, overflow: 'hidden' }}>
          {/* Sidebar */}
          <aside
            style={{
              width: 80, flexShrink: 0, height: '100%',
              backgroundColor: 'rgba(250, 250, 249, 1)',
              borderRight: '1px solid rgba(172, 173, 173, 0.1)',
              overflowY: 'auto', paddingTop: 32,
              display: 'flex', flexDirection: 'column', gap: 24, alignItems: 'center',
            }}
          >
            {grouped.map((cat) => {
              const isActive = activeCategory === cat.id;
              return (
                <button
                  key={cat.id}
                  onClick={() => handleCategoryClick(cat.id)}
                  style={{
                    width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                    background: 'none', border: 'none', cursor: 'pointer', position: 'relative', padding: '0 8px',
                    color: isActive ? COLORS.primary : '#78716c',
                  }}
                >
                  {isActive && (
                    <div style={{ position: 'absolute', left: 0, top: '50%', transform: 'translateY(-50%)', width: 3, height: 32, backgroundColor: COLORS.primary, borderRadius: '0 9999px 9999px 0' }} />
                  )}
                  <div
                    style={{
                      width: 48, height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      borderRadius: 12, transition: 'all 0.2s ease',
                      backgroundColor: isActive ? '#ea580c' : COLORS.surfaceContainer,
                      color: isActive ? '#fff' : 'inherit',
                      boxShadow: isActive ? '0 4px 12px rgba(124, 45, 18, 0.2)' : 'none',
                    }}
                  >
                    {getCategoryIcon(cat.name, isActive)}
                  </div>
                  <span style={{ fontFamily: FONTS.headline, fontWeight: isActive ? 600 : 500, fontSize: 10, textAlign: 'center' }}>
                    {cat.name}
                  </span>
                </button>
              );
            })}
          </aside>

          {/* Content */}
          <section ref={contentSectionRef} style={{ flex: 1, overflowY: 'auto', padding: '24px 16px', paddingBottom: itemCount > 0 ? 160 : 24 }}>
            {grouped.map((cat) => (
              <div key={cat.id} ref={(ref) => { if (ref) categoryRefs.current[cat.id] = ref; }} style={{ marginBottom: 32 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24 }}>
                  <div style={{ display: 'flex', color: COLORS.primary }}>
                    {getCategoryIcon(cat.name, true)}
                  </div>
                  <h2 style={{ fontFamily: FONTS.headline, fontSize: 20, fontWeight: 700, letterSpacing: '-0.01em', color: COLORS.onSurface, margin: 0 }}>
                    {cat.name}
                  </h2>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                  {cat.products.map((p) => (
                    <ProductCard
                      key={p.id} product={p} language={i18n.language}
                      quantity={getQuantity(p.id)}
                      onAdd={() => handleAdd(p)}
                      onRemove={() => handleRemove(p.id)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </section>
        </div>

        {/* Sticky Cart Bar */}
        {itemCount > 0 && (
          <div
            onClick={() => navigate('/checkout')}
            style={{
              position: 'fixed', bottom: 0, width: '100%', zIndex: 40, padding: '8px 16px 24px',
              cursor: 'pointer',
            }}
          >
            <div
              style={{
                backgroundColor: 'rgba(124, 45, 18, 0.9)', backdropFilter: 'blur(20px)',
                borderRadius: 16, padding: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                boxShadow: '0 8px 30px rgba(0,0,0,0.15)',
                transition: 'transform 0.15s ease',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div style={{ position: 'relative' }}>
                  <div style={{
                    width: 48, height: 48, borderRadius: '50%', backgroundColor: COLORS.primaryContainer,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', color: COLORS.onPrimaryContainer,
                  }}>
                    <Icon name="shopping_bag" fill size={24} />
                  </div>
                  <span style={{
                    position: 'absolute', top: -4, right: -4,
                    backgroundColor: '#fff', color: COLORS.primary, fontSize: 10, fontWeight: 800,
                    width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    borderRadius: '50%', border: `2px solid ${COLORS.primaryContainer}`,
                  }}>
                    {itemCount}
                  </span>
                </div>
                <div>
                  <div style={{ fontFamily: FONTS.headline, fontWeight: 800, color: '#fff', fontSize: 18 }}>
                    {formatPrice(cartTotal, i18n.language)}
                  </div>
                  <div style={{ fontFamily: FONTS.body, fontSize: 11, color: 'rgba(255,255,255,0.7)', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 700 }}>
                    {t('menu.checkout', 'Tap to view cart')}
                  </div>
                </div>
              </div>
              <Icon name="chevron_right" style={{ color: 'rgba(255,255,255,0.5)', fontSize: 28 }} />
            </div>
          </div>
        )}
      </div>
    </ArtisanLayout>
  );
}
