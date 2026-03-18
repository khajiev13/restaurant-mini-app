import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Section, Cell, Button, Input, Title } from '@telegram-apps/telegram-ui';
import { useCartStore } from '../stores/cartStore';
import { createOrder } from '../services/api';

export default function CartPage() {
  const items = useCartStore((s) => s.items);
  const updateQuantity = useCartStore((s) => s.updateQuantity);
  const removeItem = useCartStore((s) => s.removeItem);
  const clearCart = useCartStore((s) => s.clearCart);
  const total = useCartStore((s) => s.getTotal());
  const navigate = useNavigate();

  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handlePlaceOrder = async () => {
    if (!phone) {
      alert('Please enter your phone number');
      return;
    }
    if (!address) {
      alert('Please enter a delivery address');
      return;
    }

    setSubmitting(true);
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
      navigate(`/order/${orderId}`);
    } catch (err) {
      console.error('Order failed:', err);
      alert('Failed to place order. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

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
    <div style={{ paddingBottom: 100 }}>
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
                  onClick={() => updateQuantity(item.id, item.quantity - 1)}
                >
                  −
                </Button>
                <span>{item.quantity}</span>
                <Button
                  size="s"
                  mode="bezeled"
                  onClick={() => updateQuantity(item.id, item.quantity + 1)}
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

      <Section header="Delivery Details">
        <Input
          header="Phone Number"
          placeholder="+998 90 123 45 67"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
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

      <div
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          padding: 16,
          background: 'var(--tg-theme-bg-color, #fff)',
          borderTop: '1px solid var(--tg-theme-hint-color, #ccc)',
        }}
      >
        <Button
          size="l"
          stretched
          onClick={handlePlaceOrder}
          disabled={submitting}
        >
          {submitting
            ? 'Placing Order...'
            : `Place Order — ${total.toLocaleString()} сум`}
        </Button>
      </div>
    </div>
  );
}
