import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Section, Cell, Badge, Button, Spinner, Title } from '@telegram-apps/telegram-ui';
import { getMenu } from '../services/api';
import { useCartStore } from '../stores/cartStore';

export default function MenuPage() {
  const [menu, setMenu] = useState(null);
  const [loading, setLoading] = useState(true);
  const addItem = useCartStore((s) => s.addItem);
  const itemCount = useCartStore((s) => s.getItemCount());
  const navigate = useNavigate();

  useEffect(() => {
    getMenu()
      .then((res) => setMenu(res.data.data))
      .catch((err) => console.error('Menu fetch failed:', err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
        <Spinner size="l" />
      </div>
    );
  }

  const categories = menu?.categories || [];
  const items = menu?.items || [];

  // Group items by category
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
      <div style={{ textAlign: 'center', padding: '16px 0 8px' }}>
        <Title weight="1" style={{ fontSize: 22 }}>
          Mr.Pub
        </Title>
      </div>

      {grouped.map((category) => (
        <Section key={category.id} header={category.name}>
          {category.products.map((product) => (
            <Cell
              key={product.id}
              subtitle={`${product.price.toLocaleString()} сум`}
              after={
                <Button
                  size="s"
                  mode="bezeled"
                  onClick={(e) => {
                    e.stopPropagation();
                    addItem(product);
                  }}
                >
                  +
                </Button>
              }
              description={product.description || undefined}
            >
              {product.name}
            </Cell>
          ))}
        </Section>
      ))}

      {itemCount > 0 && (
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
            onClick={() => navigate('/cart')}
          >
            Cart ({itemCount})
          </Button>
        </div>
      )}
    </div>
  );
}
