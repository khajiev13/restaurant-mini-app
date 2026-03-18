import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Section, Cell, Button, Input, Title } from '@telegram-apps/telegram-ui';
import {
  showBackButton, hideBackButton, onBackButtonClick, offBackButtonClick,
  setMainButtonParams, onMainButtonClick, offMainButtonClick,
  mountMainButton, unmountMainButton,
  requestContact,
  hapticFeedbackNotificationOccurred, hapticFeedbackImpactOccurred,
} from '@telegram-apps/sdk-react';
import { useCartStore } from '../stores/cartStore';
import { createOrder } from '../services/api';

// Use native Telegram popups; fall back to browser for non-TG environments
const tgAlert = (msg) => {
  const tg = window.Telegram?.WebApp;
  if (tg) tg.showAlert(msg);
  else alert(msg);
};

const tgConfirm = (msg, cb) => {
  const tg = window.Telegram?.WebApp;
  if (tg) tg.showConfirm(msg, cb);
  else cb(window.confirm(msg));
};

export default function CartPage() {
  const items = useCartStore((s) => s.items);
  const updateQuantity = useCartStore((s) => s.updateQuantity);
  const clearCart = useCartStore((s) => s.clearCart);
  const total = useCartStore((s) => s.getTotal());
  const navigate = useNavigate();

  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Native back button
  const goBack = useCallback(() => navigate('/'), [navigate]);

  useEffect(() => {
    try {
      showBackButton();
      onBackButtonClick(goBack);
    } catch {}
    return () => {
      try {
        offBackButtonClick(goBack);
        hideBackButton();
      } catch {}
    };
  }, [goBack]);

  // Warn user before closing Telegram when cart has items
  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    if (items.length > 0) {
      tg.enableClosingConfirmation();
    }
    return () => tg.disableClosingConfirmation();
  }, [items.length]);

  // Request phone from Telegram
  const handleRequestPhone = async () => {
    try {
      const result = await requestContact();
      setPhone(result.contact.phoneNumber);
      try { hapticFeedbackNotificationOccurred('success'); } catch {}
    } catch {
      tgAlert('Could not retrieve your phone number. Please enter it manually below.');
    }
  };

  // Show popup helper — kept for complex multi-button dialogs
  const showAlert = tgAlert;

  // Place order logic
  const handlePlaceOrder = useCallback(async () => {
    if (!phone) {
      showAlert('Please share your phone number to place an order.');
      return;
    }
    if (!address) {
      showAlert('Please enter a delivery address.');
      return;
    }

    setSubmitting(true);
    try {
      setMainButtonParams({ is_progress_visible: true, is_active: false });
    } catch {}

    try {
      const res = await createOrder({
        items: items.map((item) => ({
          id: item.id,
          quantity: item.quantity,
          price: item.price,
          modifications: [],
        })),
        phone_number: phone,
        delivery_address: address,
        comment: comment || undefined,
        payment_method: 'cash',
        discriminator: 'delivery',
      });

      const orderId = res.data.data.id;
      clearCart();
      try { hapticFeedbackNotificationOccurred('success'); } catch {}
      navigate(`/order/${orderId}`);
    } catch (err) {
      console.error('Order failed:', err);
      tgAlert('Something went wrong. Please try again.');
      try { hapticFeedbackNotificationOccurred('error'); } catch {}
    } finally {
      setSubmitting(false);
      try { setMainButtonParams({ is_progress_visible: false, is_active: true }); } catch {}
    }
  }, [phone, address, comment, items, clearCart, navigate]);

  // Main Button → Place Order
  useEffect(() => {
    if (items.length === 0) return;
    try {
      mountMainButton();
      setMainButtonParams({
        text: `Place Order — ${total.toLocaleString()} сум`,
        is_visible: true,
        is_active: !submitting,
      });
      onMainButtonClick(handlePlaceOrder);
    } catch {}

    return () => {
      try {
        offMainButtonClick(handlePlaceOrder);
        setMainButtonParams({ is_visible: false });
        unmountMainButton();
      } catch {}
    };
  }, [items.length, total, submitting, handlePlaceOrder]);

  if (items.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Title weight="2" style={{ marginBottom: 16 }}>
          Your cart is empty
        </Title>
        <Button size="l" onClick={() => navigate('/')}>
          Browse Menu
        </Button>
      </div>
    );
  }

  return (
    <div style={{ paddingBottom: 80 }}>
      <Section header="Your Order">
        {items.map((item) => (
          <Cell
            key={item.id}
            subtitle={`${item.price.toLocaleString()} × ${item.quantity} = ${(item.price * item.quantity).toLocaleString()} сум`}
            after={
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <Button
                  size="s"
                  mode="bezeled"
                  onClick={() => {
                    updateQuantity(item.id, item.quantity - 1);
                    try { hapticFeedbackImpactOccurred('light'); } catch {}
                  }}
                >
                  −
                </Button>
                <span>{item.quantity}</span>
                <Button
                  size="s"
                  mode="bezeled"
                  onClick={() => {
                    updateQuantity(item.id, item.quantity + 1);
                    try { hapticFeedbackImpactOccurred('light'); } catch {}
                  }}
                >
                  +
                </Button>
              </div>
            }
          >
            {item.name}
          </Cell>
        ))}
      </Section>

      <Section header="Phone Number">
        <Cell
          after={
            <Button size="s" mode="bezeled" onClick={handleRequestPhone}>
              Share via Telegram
            </Button>
          }
          subtitle={phone || 'Not provided'}
        >
          Phone
        </Cell>
        <Input
          placeholder="+998 90 123 45 67"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
      </Section>

      <Section header="Delivery Details">
        <Input
          header="Delivery Address"
          placeholder="Street, building, apartment"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
        />
        <Input
          header="Comment (optional)"
          placeholder="Special instructions..."
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      </Section>
    </div>
  );
}
