import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Section, Cell, Spinner, Title } from '@telegram-apps/telegram-ui';
import { getOrderStatus, getOrder } from '../services/api';

const STATUS_LABELS = {
  NEW: 'Order Placed',
  ACCEPTED_BY_RESTAURANT: 'Being Prepared',
  READY: 'Ready for Pickup',
  TAKEN_BY_COURIER: 'On the Way',
  CANCELED: 'Cancelled',
};

export default function OrderStatusPage() {
  const { orderId } = useParams();
  const [order, setOrder] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getOrder(orderId)
      .then((res) => setOrder(res.data.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [orderId]);

  // Poll for status updates every 15 seconds
  useEffect(() => {
    const poll = () => {
      getOrderStatus(orderId)
        .then((res) => setStatus(res.data.data))
        .catch(console.error);
    };

    poll();
    const interval = setInterval(poll, 15000);
    return () => clearInterval(interval);
  }, [orderId]);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
        <Spinner size="l" />
      </div>
    );
  }

  const currentStatus = status?.status || order?.status || 'NEW';
  const terminated = currentStatus === 'CANCELED' || currentStatus === 'TAKEN_BY_COURIER';

  return (
    <div style={{ padding: 16 }}>
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <Title weight="1" style={{ fontSize: 22, marginBottom: 8 }}>
          Mr.Pub
        </Title>
        <Title weight="2" style={{ fontSize: 28, marginBottom: 4 }}>
          {STATUS_LABELS[currentStatus] || currentStatus}
        </Title>
        {status?.order_number && (
          <Title weight="3" style={{ fontSize: 16, opacity: 0.6 }}>
            Order #{status.order_number}
          </Title>
        )}
      </div>

      <Section header="Order Details">
        <Cell subtitle={`ID: ${orderId.slice(0, 8)}...`}>
          Internal Order
        </Cell>
        {status?.alipos_order_id && (
          <Cell subtitle={status.alipos_order_id.slice(0, 8) + '...'}>
            AliPOS Reference
          </Cell>
        )}
        <Cell subtitle={`${order?.total_amount?.toLocaleString()} сум`}>
          Total
        </Cell>
        <Cell subtitle={order?.payment_method}>Payment</Cell>
      </Section>

      {order?.items && (
        <Section header="Items">
          {order.items.map((item, i) => (
            <Cell key={i} subtitle={`${item.quantity}× ${item.price.toLocaleString()} сум`}>
              {item.name || `Item ${i + 1}`}
            </Cell>
          ))}
        </Section>
      )}

      {!terminated && (
        <div style={{ textAlign: 'center', marginTop: 24, opacity: 0.5, fontSize: 14 }}>
          Updating every 15 seconds...
        </div>
      )}
    </div>
  );
}
