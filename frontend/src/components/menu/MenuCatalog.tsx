import { useEffect, useMemo, useRef, useState } from 'react';
import { COLORS, FONTS, Icon } from '../artisan/ArtisanLayout';
import { formatPrice } from '../../utils/format';
import type { MenuCategory, MenuData, MenuItem } from '../../types/api';
import catBaliqlar from '../../assets/categories/baliqlar.jpg';
import catChoy from '../../assets/categories/choy.jpg';
import catOvqat from '../../assets/categories/ovqat.jpg';
import catSomsa from '../../assets/categories/somsa.jpg';
import catSuvlar from '../../assets/categories/suvlar.jpg';

export interface MenuCatalogLabels {
  soldOut: string;
  add: string;
  remove: string;
  limit: string;
  empty: string;
}

interface MenuCatalogBaseProps {
  menu: MenuData;
  language: string;
  labels: MenuCatalogLabels;
  notice?: string | null;
}

export type MenuCatalogProps = MenuCatalogBaseProps & (
  | {
      mode: 'browse';
      quantities?: never;
      onAdd?: never;
      onRemove?: never;
    }
  | {
      mode: 'interactive';
      quantities: Record<string, number>;
      onAdd: (item: MenuItem) => void;
      onRemove: (itemId: string) => void;
    }
);

interface GroupedCategory extends MenuCategory {
  products: MenuItem[];
}

type ProductCardProps = Pick<MenuCatalogBaseProps, 'language' | 'labels'> & {
  product: MenuItem;
} & (
    | {
        mode: 'browse';
        quantities?: never;
        onAdd?: never;
        onRemove?: never;
      }
    | {
        mode: 'interactive';
        quantities: Record<string, number>;
        onAdd: (item: MenuItem) => void;
        onRemove: (itemId: string) => void;
      }
  );

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
    position: 'relative',
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
      WebkitUserSelect: 'none',
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

function ProductCard(props: ProductCardProps) {
  const { product } = props;
  const imgUrl = product.images?.[0]?.url;
  const available = product.available !== false;
  const interactive = props.mode === 'interactive';
  const quantity = interactive ? props.quantities[product.id] ?? 0 : 0;
  const atLimit = product.availableCount !== null && quantity >= product.availableCount;

  return (
    <div
      style={{
        backgroundColor: COLORS.surfaceContainerLowest, borderRadius: 12, padding: 12,
        display: 'flex', gap: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
        border: `1px solid rgba(172, 173, 173, 0.05)`,
        opacity: available ? 1 : 0.72,
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
            {formatPrice(product.price, props.language)}
          </span>
          {!available ? (
            <span style={{
              minHeight: 36, display: 'inline-flex', alignItems: 'center', padding: '0 12px',
              borderRadius: 999, background: 'rgba(179, 27, 37, 0.09)', color: COLORS.error,
              fontSize: 11, fontWeight: 800,
            }}>
              {props.labels.soldOut}
            </span>
          ) : interactive && quantity > 0 ? (
            <div style={{
              display: 'flex', alignItems: 'center',
              backgroundColor: 'rgba(255, 121, 65, 0.2)',
              borderRadius: 9999, padding: 4,
            }}>
              <button
                type="button"
                aria-label={`${product.name} ${props.labels.remove}`}
                onClick={() => props.onRemove(product.id)}
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
                type="button"
                aria-label={atLimit ? props.labels.limit : `${product.name} ${props.labels.add}`}
                onClick={() => props.onAdd(product)}
                disabled={atLimit}
                style={{
                  width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  borderRadius: '50%', backgroundColor: atLimit ? COLORS.surfaceContainerHigh : COLORS.primary,
                  color: atLimit ? COLORS.secondary : '#fff', border: 'none', cursor: atLimit ? 'default' : 'pointer',
                  boxShadow: atLimit ? 'none' : '0 2px 6px rgba(163, 56, 0, 0.3)',
                }}
              >
                <Icon name="add" size={16} />
              </button>
            </div>
          ) : interactive ? (
            <button
              type="button"
              aria-label={`${product.name} ${props.labels.add}`}
              onClick={() => props.onAdd(product)}
              style={{
                width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center',
                borderRadius: '50%', backgroundColor: COLORS.primary, color: '#fff',
                border: 'none', cursor: 'pointer',
                boxShadow: '0 4px 12px rgba(163, 56, 0, 0.25)',
              }}
            >
              <Icon name="add" />
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default function MenuCatalog(props: MenuCatalogProps) {
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const categoryRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const contentSectionRef = useRef<HTMLElement>(null);
  const isScrollingByClick = useRef(false);
  const activeCategoryRef = useRef<string | null>(null);

  const grouped: GroupedCategory[] = useMemo(() => {
    const categories = [...props.menu.categories].sort((a, b) => a.sortOrder - b.sortOrder);
    const items = [...props.menu.items].sort((a, b) => a.sortOrder - b.sortOrder);

    return categories
      .map((category) => ({
        ...category,
        products: items.filter((item) => item.categoryId === category.id),
      }))
      .filter((category) => category.products.length > 0);
  }, [props.menu.categories, props.menu.items]);

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

      for (const category of grouped) {
        const element = categoryRefs.current[category.id];
        if (!element) continue;
        const distance = Math.abs(element.getBoundingClientRect().top - containerTop);
        if (distance < closestDistance) {
          closestDistance = distance;
          closestId = category.id;
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

  const hasCartItems = props.mode === 'interactive'
    && Object.values(props.quantities).some((quantity) => quantity > 0);

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
      <aside
        style={{
          width: 80, flexShrink: 0, height: '100%',
          backgroundColor: 'rgba(250, 250, 249, 1)',
          borderRight: '1px solid rgba(172, 173, 173, 0.1)',
          overflowY: 'auto', paddingTop: 32,
          display: 'flex', flexDirection: 'column', gap: 24, alignItems: 'center',
        }}
      >
        {grouped.map((category) => {
          const isActive = activeCategory === category.id;
          return (
            <button
              type="button"
              key={category.id}
              onClick={() => handleCategoryClick(category.id)}
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
                {getCategoryIcon(category.name, isActive)}
              </div>
              <span style={{ fontFamily: FONTS.headline, fontWeight: isActive ? 600 : 500, fontSize: 10, textAlign: 'center' }}>
                {category.name}
              </span>
            </button>
          );
        })}
      </aside>

      <section ref={contentSectionRef} style={{ flex: 1, overflowY: 'auto', padding: '24px 16px', paddingBottom: hasCartItems ? 160 : 24 }}>
        {props.notice && (
          <div role="status" style={{
            marginBottom: 16, padding: '10px 12px', borderRadius: 12,
            background: '#fff7ed', color: COLORS.onPrimaryContainer,
            fontSize: 12, fontWeight: 700, lineHeight: 1.45,
          }}>
            {props.notice}
          </div>
        )}
        {grouped.length === 0 ? (
          <p style={{ fontFamily: FONTS.body, color: COLORS.onSurfaceVariant }}>{props.labels.empty}</p>
        ) : grouped.map((category) => (
          <div key={category.id} ref={(ref) => { if (ref) categoryRefs.current[category.id] = ref; }} style={{ marginBottom: 32 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24 }}>
              <div style={{ display: 'flex', color: COLORS.primary }}>
                {getCategoryIcon(category.name, true)}
              </div>
              <h2 style={{ fontFamily: FONTS.headline, fontSize: 20, fontWeight: 700, letterSpacing: '-0.01em', color: COLORS.onSurface, margin: 0 }}>
                {category.name}
              </h2>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {category.products.map((product) => (
                props.mode === 'interactive' ? (
                  <ProductCard
                    key={product.id}
                    product={product}
                    language={props.language}
                    labels={props.labels}
                    mode="interactive"
                    quantities={props.quantities}
                    onAdd={props.onAdd}
                    onRemove={props.onRemove}
                  />
                ) : (
                  <ProductCard
                    key={product.id}
                    product={product}
                    language={props.language}
                    labels={props.labels}
                    mode="browse"
                  />
                )
              ))}
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
