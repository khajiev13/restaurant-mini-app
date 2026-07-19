import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ArtisanLayout, { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import TableCodeSheet from '../../components/artisan/TableCodeSheet';
import TableContextBar from '../../components/artisan/TableContextBar';
import MenuCatalog from '../../components/menu/MenuCatalog';
import { getMe } from '../../services/api';
import { useAuthStore } from '../../stores/authStore';
import { useCartStore } from '../../stores/cartStore';
import { useMenuStore } from '../../stores/menuStore';
import { useTableOrderStore } from '../../stores/tableOrderStore';
import { formatPrice } from '../../utils/format';
import type { MenuData, MenuItem } from '../../types/api';

const tg = window.Telegram?.WebApp;
const haptic = tg?.HapticFeedback;
const EMPTY_MENU: MenuData = { categories: [], items: [] };

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
  const reconcileAvailability = useCartStore((s) => s.reconcileAvailability);
  const tableContext = useTableOrderStore((s) => s.context);
  const resolveCode = useTableOrderStore((s) => s.resolveCode);
  const tableResolving = useTableOrderStore((s) => s.isResolving);
  const tableError = useTableOrderStore((s) => s.error);
  const clearTableError = useTableOrderStore((s) => s.clearError);
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const [avatarUrl, setAvatarUrl] = useState<string | undefined>();
  const [firstName, setFirstName] = useState<string | undefined>();
  const [tableSheetOpen, setTableSheetOpen] = useState(false);
  const [cartNotice, setCartNotice] = useState<string | null>(null);

  const quantities = useMemo(
    () => Object.fromEntries(cartItems.map((item) => [item.id, item.quantity])),
    [cartItems],
  );

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

  useEffect(() => {
    if (!menu?.items) return;
    const adjustment = reconcileAvailability(menu.items);
    if (adjustment.removed > 0 || adjustment.reduced > 0) {
      setCartNotice(t('menu.cart_adjusted', "Mavjudlik o'zgargani uchun savat yangilandi."));
    }
  }, [menu?.items, reconcileAvailability, t]);

  useEffect(() => {
    if (tableError && !tableContext) setTableSheetOpen(true);
  }, [tableContext, tableError]);

  // Hide Telegram's MainButton in Artisan theme — we use our own cart bar
  useEffect(() => {
    const mainButton = tg?.MainButton;
    if (!mainButton) return;
    mainButton.setParams({ is_visible: false });
    return () => { mainButton.setParams({ is_visible: false }); };
  }, []);

  const handleAdd = (product: MenuItem) => { addItem(product); haptic?.impactOccurred('light'); };
  const handleRemove = (id: string) => {
    const item = cartItems.find((cartItem) => cartItem.id === id);
    if (item && item.quantity > 1) updateQuantity(id, item.quantity - 1);
    else removeItem(id);
    haptic?.impactOccurred('light');
  };

  const openTableSheet = () => {
    clearTableError();
    setTableSheetOpen(true);
  };

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
          <button type="button" onClick={() => void retry()} style={{ background: COLORS.primary, color: '#fff', padding: '10px 24px', borderRadius: 8, border: 'none', fontWeight: 600, cursor: 'pointer' }}>
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
        <div style={{ paddingTop: 64, flexShrink: 0 }}>
          <TableContextBar context={tableContext} onChange={openTableSheet} />
        </div>
        <MenuCatalog
          menu={menu ?? EMPTY_MENU}
          language={i18n.language}
          mode="interactive"
          labels={{
            soldOut: t('menu.sold_out', "Sotuvda yo'q"),
            add: t('menu.add', 'Add'),
            remove: t('menu.remove', 'Remove'),
            limit: t('menu.limit', 'Available quantity is already in the cart'),
            empty: t('menu.empty', 'No menu items'),
          }}
          quantities={quantities}
          onAdd={handleAdd}
          onRemove={handleRemove}
          notice={cartNotice}
        />

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
      <TableCodeSheet
        open={tableSheetOpen}
        onClose={() => {
          setTableSheetOpen(false);
          clearTableError();
        }}
        onResolve={resolveCode}
        resolving={tableResolving}
        error={tableError}
      />
    </ArtisanLayout>
  );
}
