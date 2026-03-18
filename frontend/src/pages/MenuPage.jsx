import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Section, Cell, Button, Spinner, Title } from '@telegram-apps/telegram-ui';
import { getMenu } from '../services/api';
import { useCartStore } from '../stores/cartStore';
import logo from '../assets/logo.png';

export default function MenuPage() {
  const [menu, setMenu] = useState(null);
  const [loading, setLoading] = useState(true);
  const addItem = useCartStore((s) => s.addItem);
  const itemCount = useCartStore((s) => s.getItemCount());
  const navigate = useNavigate();

  const goToCart = useCallback(() => navigate('/cart'), [navigate]);

  // Hide native back button on root page
  useEffect(() => {
    window.Telegram?.WebApp?.BackButton?.hide();
  }, []);

  // Native Telegram Main Button shows cart count
  useEffect(() => {
    const MainButton = window.Telegram?.WebApp?.MainButton;
    if (!MainButton) return;

    MainButton.offClick(goToCart);

    if (itemCount > 0) {
      MainButton.setParams({
        text: `🛒 Cart (${itemCount})`,
        is_active: true,
        is_visible: true,
      });
      MainButton.onClick(goToCart);
    } else {
      MainButton.setParams({ is_visible: false });
    }

    return () => {
      MainButton.offClick(goToCart);
      MainButton.setParams({ is_visible: false });
    };
  }, [itemCount, goToCart]);

  useEffect(() => {
    getMenu()
      .then((res) => setMenu(res.data.data))
      .catch((err) => console.error('Menu fetch failed:', err))
      .finally(() => setLoading(false));
  }, []);

  const handleAddItem = (product) => {
    addItem(product);
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light');
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 60, minHeight: '80vh' }}>
        <img src={logo} alt="OLOT SOMSA" style={{ width: 80, height: 80, borderRadius: 16, marginBottom: 16 }} />
        <Spinner size="l" />
      </div>
    );
  }

  const categories = menu?.categories || [];
  const items = menu?.items || [];

  const grouped = categories
    .sort((a, b) => a.sortOrder - b.sortOrder)
    .map((cat) => ({
      ...cat,
      products: items
        .filter((item) => item.categoryId === cat.id)
        .sort((a, b) => a.sortOrder - b.sortOrder),
    }))
    .filter((cat) => cat.products.length > 0);

  return (
    <div style={{ paddingBottom: 80 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <img src={logo} alt="OLOT SOMSA" style={{ width: 36, height: 36, borderRadius: 8 }} />
          <Title weight="1" style={{ fontSize: 20 }}>OLOT SOMSA</Title>
        </div>
        <Button size="s" mode="bezeled" onClick={() => navigate('/profile')}>
          Profile
        </Button>
      </div>

      {grouped.map((category) => (
        <Section key={category.id} header={category.name}>
          {category.products.map((product) => {
            const imgUrl = product.images?.[0]?.url;
            return (
              <Cell
                key={product.id}
                subtitle={`${product.price.toLocaleString()} сум`}
                before={
                  imgUrl ? (
                    <img src={imgUrl} alt={product.name} style={{ width: 48, height: 48, borderRadius: 8, objectFit: 'cover' }} />
                  ) : undefined
                }
                after={
                  <Button size="s" mode="bezeled" onClick={(e) => { e.stopPropagation(); handleAddItem(product); }}>
                    +
                  </Button>
                }
                description={product.description || undefined}
              >
                {product.name}
              </Cell>
            );
          })}
        </Section>
      ))}
    </div>
  );
}
