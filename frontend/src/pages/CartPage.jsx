import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Section, Cell, Button, Input, Title } from '@telegram-apps/telegram-ui';
import { requestContact } from '@telegram-apps/sdk-react';
import { useCartStore } from '../stores/cartStore';
import { createOrder } from '../services/api';

const tgAlert = (msg) => {
  const tg = window.Telegram?.WebApp;
  if (tg) tg.showAlert(msg);
  else alert(msg);
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
    const BackButton = window.Telegram?.WebApp?.BackButton;
    if (!BackButton) return;
    BackButton.offClick(goBack);
    BackButton.onClick(goBack);
    BackButton.show();
    return () => {
      BackButton.offClick(goBack);
      BackButton.hide();
    };
  }, [goBack]);

  // Warn before closing Telegram when cart has items
  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    if (items.length > 0) tg.enableClosingConfirmation();
    return () => tg.disableClosingConfirmation();
  }, [items.length]);

  // Request phone number via native Telegram dialog
  const handleRequestPhone = async () => {
    try {
      const result = await requestContact();
      setPhone(result.contact.phoneNumber);
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('success');
    } catch {
      tgAlert('Could not retrieve your phone number. Please enter it manually below.');
    }
  };

  // Place order
  const handlePlaceOrder = useCallback(async () => {
    if (!phone) { tgAlert('Please share your phone number to place an order.'); return; }
    if (!address) { tgAlert('Please enter a delivery address.'); return; }

    const MainButton = window.Telegram?.WebApp?.MainButton;
    setSubmitting(true);
    if (MainButton) { MainButton.showProgress(false); MainButton.disable(); }

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
      clearCart();
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('success');
      navigate(`/order/${res.data.data.id}`);
    } catch (err) {
      console.error('Order failed:', err);
      tgAlert('Something went wrong. Please try again.');
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('error');
    } finally {
      setSubmitting(false);
      if (MainButton) { MainButton.hideProgress(); MainButton.enable(); }
    }
  }, [phone, address, comment, items, clearCart, navigate]);

  // Native Main Button → Place Order
  useEffect(() => {
    const MainButton = window.Telegram?.WebApp?.MainButton;
    if (!MainButton || items.length === 0) return;

    MainButton.offClick(handlePlaceOrder);
    MainButton.setParams({
      text: `Place Order — ${total.toLocaleString()} сум`,
      is_active: !submitting,
      is_visible: true,
    });
    MainButton.onClick(handlePlaceOrder);

    return () => {
      MainButton.offClick(handlePlaceOrder);
      MainButton.setParams({ is_visible: false });
    };
  }, [items.length, total, submitting, handlePlaceOrder]);

  if (items.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Title weight="2" style={{ marginBottom: 16 }}>Your cart is empty</Title>
        <Button size="l" onClick={() => navigate('/')}>Browse Menu</Button>
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
                <Button size="s" mode="bezeled" onClick={() => {
                  updateQuantity(item.id, item.quantity - 1);
                  window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light');
                }}>−</Button>
                <span>{item.quantity}</span>
                <Button size="s" mode="bezeled" onClick={() => {
                  updateQuantity(item.id, item.quantity + 1);
                  window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light');
                }}>+</Button>
              </div>
            }
          >
            {item.name}
          </Cell>
        ))}
      </Section>

      <Section header="Phone Number">
        <Cell
          after={<Button size="s" mode="bezeled" onClick={handleRequestPhone}>Share via Telegram</Button>}
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

