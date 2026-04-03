import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ArtisanLayout, { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import { createAddress, createOrder, getAddresses, getMe } from '../../services/api';
import { useAuthStore } from '../../stores/authStore';
import { useCartStore } from '../../stores/cartStore';
import { formatPrice } from '../../utils/format';
import type { Address, CreateOrderPayload } from '../../types/api';

const tg = window.Telegram?.WebApp;
const haptic = tg?.HapticFeedback;

const PAYMENT_METHODS = [
  { key: 'cash', icon: 'payments', color: '#047857' },
  { key: 'rahmat', icon: 'credit_card', color: '#0369a1' },
] as const;

type PaymentMethodKey = typeof PAYMENT_METHODS[number]['key'];

interface AddressFormState {
  label: string; address: string; entrance: string; apartment: string;
  floor: string; doorCode: string; instructions: string; lat: number | null; lng: number | null;
}

const EMPTY_FORM: AddressFormState = {
  label: '', address: '', entrance: '', apartment: '',
  floor: '', doorCode: '', instructions: '', lat: null, lng: null,
};

const tgAlert = (msg: string, setToast: (m: string) => void) => { setToast(msg); haptic?.notificationOccurred('error'); };

function InputField({ label, placeholder, value, onChange, required, type = 'text' }: {
  label: string; placeholder?: string; value: string;
  onChange: (v: string) => void; required?: boolean; type?: string;
}) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 10, fontWeight: 700, color: COLORS.secondary, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4, marginLeft: 4, fontFamily: FONTS.body }}>
        {label}{required ? ' *' : ''}
      </label>
      <input
        type={type} placeholder={placeholder} value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: '100%', backgroundColor: COLORS.surfaceContainerLowest, border: 'none', borderRadius: 8,
          padding: 12, fontSize: 14, fontFamily: FONTS.body, color: COLORS.onSurface, outline: 'none',
          boxSizing: 'border-box',
        }}
      />
    </div>
  );
}

export default function ArtisanCheckoutPage() {
  const { t, i18n } = useTranslation();
  const items = useCartStore((s) => s.items);
  const clearCart = useCartStore((s) => s.clearCart);
  const total = useCartStore((s) => s.getTotal());
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const authenticate = useAuthStore((s) => s.authenticate);
  const navigate = useNavigate();

  const [phone, setPhone] = useState('');
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [selectedAddressId, setSelectedAddressId] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<AddressFormState>(EMPTY_FORM);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethodKey>('cash');
  const [toast, setToast] = useState('');
  const showToast = (msg: string) => showToast(msg, setToast);
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(''), 3000); return () => clearTimeout(t); }, [toast]);

  const stateRef = useRef({ phone, selectedAddressId, addresses, comment, items, clearCart, navigate, submitting, paymentMethod });
  stateRef.current = { phone, selectedAddressId, addresses, comment, items, clearCart, navigate, submitting, paymentMethod };

  useEffect(() => {
    const bb = tg?.BackButton;
    if (!bb) return;
    const h = () => navigate('/');
    bb.onClick(h); bb.show();
    return () => { bb.offClick(h); bb.hide(); };
  }, [navigate]);

  useEffect(() => { if (items.length === 0) navigate('/', { replace: true }); }, [items.length, navigate]);

  useEffect(() => {
    let cancelled = false;

    if (!isAuthenticated) {
      setLoading(false);
      return;
    }

    setLoading(true);

    void Promise.all([getMe(), getAddresses()])
      .then(([meRes, addrRes]) => {
        if (cancelled) return;
        const p = meRes.data.data?.phone_number;
        if (p) setPhone(p);
        const addrs = addrRes.data.data || [];
        setAddresses(addrs);
        if (addrs.length > 0) setSelectedAddressId(addrs[0].id);
      })
      .catch(console.error)
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [isAuthenticated]);

  const handlePlaceOrder = async () => {
    const s = stateRef.current;
    if (s.submitting) return;
    if (!s.phone) { showToast(t('checkout.error_phone')); return; }
    const addr = s.addresses.find((a) => a.id === s.selectedAddressId);
    if (!addr) { showToast(t('checkout.error_address')); return; }

    setSubmitting(true);
    try {
      const payload: CreateOrderPayload = {
        items: s.items.map((i) => ({ id: i.id, quantity: i.quantity, price: i.price, modifications: [] })),
        phone_number: s.phone, delivery_address: addr.full_address,
        latitude: addr.latitude, longitude: addr.longitude, address_id: addr.id,
        comment: s.comment || undefined, payment_method: s.paymentMethod, discriminator: 'delivery',
      };
      const res = await createOrder(payload);
      s.clearCart();
      haptic?.notificationOccurred('success');

      const orderData = res.data.data;

      if (s.paymentMethod === 'rahmat' && orderData.multicard_checkout_url) {
        // Open payment URL first — before navigation so the openLink call is not lost on re-render
        if (tg?.openLink) {
          tg.openLink(orderData.multicard_checkout_url);
        } else {
          window.open(orderData.multicard_checkout_url, '_blank');
        }
        s.navigate(`/order/${orderData.id}`);
      } else {
        s.navigate(`/order/${orderData.id}`);
      }
    } catch (err) {
      console.error('Order failed:', err);
      showToast(t('checkout.error_general'));
      haptic?.notificationOccurred('error');
    } finally { setSubmitting(false); }
  };

  const handleSaveAddress = async () => {
    if (!form.address.trim()) { showToast(t('checkout.error_enter_address')); return; }
    if (saving) return;
    setSaving(true);
    try {
      const res = await createAddress({
        label: form.label.trim() || 'Home', full_address: form.address.trim(),
        latitude: form.lat ? String(form.lat) : null, longitude: form.lng ? String(form.lng) : null,
        entrance: form.entrance.trim() || null, apartment: form.apartment.trim() || null,
        floor: form.floor.trim() || null, door_code: form.doorCode.trim() || null,
        courier_instructions: form.instructions.trim() || null, is_default: addresses.length === 0,
      });
      const saved = res.data.data;
      setAddresses((c) => [...c, saved]);
      setSelectedAddressId(saved.id);
      setShowAddForm(false); setForm(EMPTY_FORM);
      haptic?.notificationOccurred('success');
    } catch { showToast(t('checkout.error_save_address')); }
    finally { setSaving(false); }
  };

  if (loading) {
    return (
      <ArtisanLayout showBack backTitle={t('checkout.title', 'Checkout')} hideBottomNav>
        <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
          <div style={{ width: 32, height: 32, border: `3px solid ${COLORS.surfaceContainer}`, borderTopColor: COLORS.primary, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </ArtisanLayout>
    );
  }

  if (!isAuthenticated) {
    return (
      <ArtisanLayout showBack backTitle={t('checkout.title', 'Checkout')} hideBottomNav>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '120px 24px', textAlign: 'center' }}>
          <div style={{ paddingBottom: 24 }}>
            <Icon name="shopping_bag" style={{ fontSize: 64, color: COLORS.surface }} />
          </div>
          <h2 style={{ fontFamily: FONTS.headline, fontSize: 24, color: COLORS.onSurface, margin: '0 0 8px 0' }}>{t('profile.not_logged_in_title', 'Not Logged In')}</h2>
          <p style={{ fontFamily: FONTS.body, fontSize: 16, color: COLORS.secondary, margin: '0 0 32px 0' }}>
            {t('checkout.not_logged_in_desc', 'Please log in with Telegram to place your order.')}
          </p>
          <button
            onClick={() => void authenticate()}
            style={{
              backgroundColor: COLORS.primary,
              color: COLORS.onPrimary,
              border: 'none',
              borderRadius: 12,
              padding: '16px 24px',
              fontFamily: FONTS.headline,
              fontSize: 16,
              fontWeight: 700,
              width: '100%',
              cursor: 'pointer',
            }}
          >
            {t('profile.login_button', 'Login with Telegram')}
          </button>
        </div>
      </ArtisanLayout>
    );
  }

  return (
    <ArtisanLayout showBack backTitle={t('checkout.title', 'Checkout')} hideBottomNav>
      {toast && (
        <div style={{ position: 'fixed', top: 72, left: 16, right: 16, zIndex: 100, background: '#1c1c1e', color: '#fff', borderRadius: 12, padding: '12px 16px', fontSize: 14, boxShadow: '0 4px 16px rgba(0,0,0,0.3)', textAlign: 'center' }}>
          {toast}
        </div>
      )}
      <main style={{ paddingTop: 80, paddingBottom: 160, paddingLeft: 16, paddingRight: 16, maxWidth: 672, margin: '0 auto' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {/* Phone */}
          <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 4px' }}>
              <h2 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: COLORS.secondary, fontFamily: FONTS.headline, margin: 0 }}>
                {t('checkout.phone_label')}
              </h2>
              <Icon name="verified_user" size={16} style={{ color: COLORS.primary }} />
            </div>
            <div style={{
              backgroundColor: COLORS.surfaceContainerLowest, padding: 16, borderRadius: 12,
              boxShadow: '0 1px 3px rgba(0,0,0,0.04)', border: '1px solid rgba(172,173,173,0.1)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <Icon name="phone_iphone" style={{ color: COLORS.primaryContainer }} />
                <span style={{ fontWeight: 600, color: COLORS.onSurface }}>{phone || t('checkout.no_phone', 'Not set')}</span>
              </div>
            </div>
          </section>

          {/* Addresses */}
          <section style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <h2 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: COLORS.secondary, fontFamily: FONTS.headline, margin: 0, padding: '0 4px' }}>
              {t('checkout.address_label')}
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {addresses.map((addr) => {
                const active = selectedAddressId === addr.id;
                const iconName = addr.label.toLowerCase().includes('office') ? 'work' : 'home';
                return (
                  <label
                    key={addr.id}
                    onClick={() => { setSelectedAddressId(addr.id); haptic?.selectionChanged(); }}
                    style={{
                      position: 'relative', display: 'flex', alignItems: 'flex-start', padding: 16,
                      backgroundColor: COLORS.surfaceContainerLowest, borderRadius: 12, cursor: 'pointer',
                      border: active ? `2px solid ${COLORS.primary}` : '1px solid rgba(172,173,173,0.3)',
                      boxShadow: active ? `0 0 0 4px rgba(163, 56, 0, 0.05)` : 'none',
                      transition: 'all 0.2s ease',
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <Icon name={iconName} size={18} style={{ color: active ? COLORS.primary : COLORS.secondary }} />
                        <span style={{ fontWeight: 700, color: COLORS.onSurface }}>{addr.label}</span>
                      </div>
                      <p style={{ fontSize: 14, color: COLORS.secondary, lineHeight: 1.5, margin: 0 }}>{addr.full_address}</p>
                    </div>
                    <div style={{
                      width: 20, height: 20, borderRadius: '50%', flexShrink: 0,
                      border: active ? `4px solid ${COLORS.primary}` : `1px solid ${COLORS.outline}`,
                      backgroundColor: '#fff',
                    }} />
                  </label>
                );
              })}
            </div>

            {/* Add address form */}
            {!showAddForm ? (
              <button
                onClick={() => setShowAddForm(true)}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                  padding: '12px 24px', backgroundColor: COLORS.surfaceContainerLow, borderRadius: 12,
                  color: COLORS.primary, fontWeight: 700, fontSize: 13, border: 'none', cursor: 'pointer',
                  fontFamily: FONTS.body, textTransform: 'uppercase', letterSpacing: '0.05em',
                }}
              >
                <Icon name="add" size={18} />
                {t('checkout.add_new_address')}
              </button>
            ) : (
              <div style={{
                backgroundColor: COLORS.surfaceContainerLow, padding: 20, borderRadius: 12,
                border: '1px solid rgba(172,173,173,0.2)', display: 'flex', flexDirection: 'column', gap: 16,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <h3 style={{ fontWeight: 700, color: COLORS.onSurface, margin: 0 }}>{t('checkout.new_address_header', 'Add New Address')}</h3>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12 }}>
                  <InputField label={t('checkout.address_label_input')} placeholder="e.g. Home" value={form.label} onChange={(v) => setForm((c) => ({ ...c, label: v }))} />
                  <InputField label={t('checkout.street_building')} placeholder={t('checkout.street_placeholder')} value={form.address} onChange={(v) => setForm((c) => ({ ...c, address: v }))} required />
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <InputField label={t('checkout.entrance')} value={form.entrance} onChange={(v) => setForm((c) => ({ ...c, entrance: v }))} />
                    <InputField label={t('checkout.floor')} value={form.floor} onChange={(v) => setForm((c) => ({ ...c, floor: v }))} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <InputField label={t('checkout.apartment')} value={form.apartment} onChange={(v) => setForm((c) => ({ ...c, apartment: v }))} />
                    <InputField label={t('checkout.door_code')} value={form.doorCode} onChange={(v) => setForm((c) => ({ ...c, doorCode: v }))} />
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 12, paddingTop: 8 }}>
                  <button
                    onClick={() => void handleSaveAddress()} disabled={saving}
                    style={{
                      flex: 1, padding: 12, backgroundColor: COLORS.primary, color: COLORS.onPrimary,
                      fontWeight: 700, borderRadius: 12, fontSize: 14, border: 'none', cursor: 'pointer',
                    }}
                  >
                    {saving ? t('checkout.saving') : t('checkout.save_address')}
                  </button>
                  <button
                    onClick={() => { setShowAddForm(false); setForm(EMPTY_FORM); }}
                    style={{
                      padding: '12px 24px', backgroundColor: COLORS.surfaceContainerHigh, color: COLORS.secondary,
                      fontWeight: 700, borderRadius: 12, fontSize: 14, border: 'none', cursor: 'pointer',
                    }}
                  >
                    {t('common.cancel', 'Cancel')}
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* Payment Method */}
          <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <h2 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: COLORS.secondary, fontFamily: FONTS.headline, margin: 0, padding: '0 4px' }}>
              {t('checkout.payment_method_label', '💳 Payment Method')}
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {PAYMENT_METHODS.map((pm) => {
                const active = paymentMethod === pm.key;
                return (
                  <button
                    key={pm.key}
                    onClick={() => { setPaymentMethod(pm.key); haptic?.selectionChanged(); }}
                    style={{
                      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                      gap: 8, padding: '16px 8px', borderRadius: 12, cursor: 'pointer',
                      backgroundColor: active ? COLORS.surfaceContainerLowest : COLORS.surfaceContainerLow,
                      border: active ? `2px solid ${COLORS.primary}` : '1px solid rgba(172,173,173,0.2)',
                      boxShadow: active ? '0 2px 8px rgba(163, 56, 0, 0.1)' : 'none',
                      transition: 'all 0.2s ease',
                    }}
                  >
                    <div style={{
                      width: 44, height: 44, borderRadius: '50%',
                      backgroundColor: active ? `${pm.color}15` : COLORS.surfaceContainer,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      transition: 'all 0.2s ease',
                    }}>
                      <Icon name={pm.icon} fill={active} size={22} style={{ color: active ? pm.color : COLORS.outline }} />
                    </div>
                    <span style={{
                      fontFamily: FONTS.body, fontSize: 12, fontWeight: active ? 700 : 600,
                      color: active ? COLORS.onSurface : COLORS.secondary,
                      textTransform: 'capitalize',
                    }}>
                      {t(`payment_methods.${pm.key}`)}
                    </span>
                    {active && (
                      <div style={{
                        width: 6, height: 6, borderRadius: '50%', backgroundColor: COLORS.primary,
                      }} />
                    )}
                  </button>
                );
              })}
            </div>
          </section>

          {/* Order Summary */}
          <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <h2 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: COLORS.secondary, fontFamily: FONTS.headline, margin: 0, padding: '0 4px' }}>
              {t('checkout.items_label', 'Your Selection')}
            </h2>
            <div style={{
              backgroundColor: COLORS.surfaceContainerLowest, borderRadius: 16, overflow: 'hidden',
              border: '1px solid rgba(172,173,173,0.1)',
            }}>
              {items.map((item, idx) => (
                <div
                  key={item.id}
                  style={{
                    padding: 12, display: 'flex', gap: 12, alignItems: 'center',
                    borderBottom: idx < items.length - 1 ? `1px solid ${COLORS.surfaceContainer}` : 'none',
                  }}
                >
                  {item.images?.[0]?.url && (
                    <img src={item.images[0].url} alt={item.name} style={{ width: 64, height: 64, borderRadius: 8, objectFit: 'cover' }} />
                  )}
                  <div style={{ flex: 1 }}>
                    <h4 style={{ fontWeight: 700, color: COLORS.onSurface, fontSize: 14, margin: 0 }}>
                      {item.name} (x{item.quantity})
                    </h4>
                  </div>
                  <span style={{ fontWeight: 700, color: COLORS.primary, fontFamily: FONTS.headline }}>
                    {formatPrice(item.price * item.quantity, i18n.language)}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* Comment */}
          <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <h2 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: COLORS.secondary, fontFamily: FONTS.headline, margin: 0, padding: '0 4px' }}>
              {t('checkout.comment_label')}
            </h2>
            <div style={{
              backgroundColor: COLORS.surfaceContainerLowest, padding: 4, borderRadius: 12,
              boxShadow: '0 1px 3px rgba(0,0,0,0.04)', border: '1px solid rgba(172,173,173,0.1)',
            }}>
              <textarea
                placeholder={t('checkout.comment_placeholder')}
                value={comment} onChange={(e) => setComment(e.target.value)}
                rows={3}
                style={{
                  width: '100%', backgroundColor: 'transparent', border: 'none', fontSize: 14, padding: 12,
                  fontFamily: FONTS.body, color: COLORS.onSurface, outline: 'none', resize: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>
          </section>
        </div>
      </main>

      {/* Place Order Button */}
      <div style={{ position: 'fixed', bottom: 0, left: 0, width: '100%', padding: 16, backgroundColor: 'rgba(246,246,246,0.8)', backdropFilter: 'blur(12px)', zIndex: 50 }}>
        <div style={{ maxWidth: 672, margin: '0 auto' }}>
          <button
            onClick={() => void handlePlaceOrder()} disabled={submitting}
            style={{
              width: '100%', background: 'linear-gradient(135deg, #a33800 0%, #ff7941 100%)',
              color: COLORS.onPrimary, padding: '16px 24px', borderRadius: 16,
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              border: 'none', cursor: submitting ? 'wait' : 'pointer',
              boxShadow: '0 8px 24px rgba(163, 56, 0, 0.2)',
              opacity: submitting ? 0.7 : 1, transition: 'transform 0.15s ease',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Icon name="shopping_bag" fill style={{ color: COLORS.onPrimary }} />
              <span style={{ fontWeight: 700, fontFamily: FONTS.headline, fontSize: 18, letterSpacing: '-0.01em' }}>
                {submitting ? t('checkout.placing_order', 'Placing...') : t('checkout.place_order')}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ height: 24, width: 1, backgroundColor: 'rgba(255,255,255,0.2)' }} />
              <span style={{ fontWeight: 800, fontFamily: FONTS.headline, fontSize: 18 }}>
                {formatPrice(total, i18n.language)}
              </span>
            </div>
          </button>
          <div style={{ height: 8 }} />
        </div>
      </div>
    </ArtisanLayout>
  );
}
