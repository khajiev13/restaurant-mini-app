import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Section, Cell, Spinner, Title, Button } from '@telegram-apps/telegram-ui';
import {
  showBackButton, hideBackButton, onBackButtonClick, offBackButtonClick,
  requestContact,
  hapticFeedbackNotificationOccurred,
} from '@telegram-apps/sdk-react';
import { getMe, getOrders, updateMe } from '../services/api';

const STATUS_LABELS = {
  NEW: 'Placed',
  ACCEPTED_BY_RESTAURANT: 'Preparing',
  READY: 'Ready',
  TAKEN_BY_COURIER: 'Delivered',
  CANCELED: 'Cancelled',
};

export default function ProfilePage() {
  const [user, setUser] = useState(null);
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  // Native back button
  const goHome = useCallback(() => navigate('/'), [navigate]);

  useEffect(() => {
    try {
      showBackButton();
      onBackButtonClick(goHome);
    } catch {}
    return () => {
      try {
        offBackButtonClick(goHome);
        hideBackButton();
      } catch {}
    };
  }, [goHome]);

  useEffect(() => {
    Promise.all([getMe(), getOrders()])
      .then(([userRes, ordersRes]) => {
        setUser(userRes.data.data);
        setOrders(ordersRes.data.data);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSharePhone = async () => {
    try {
      const result = await requestContact();
      const phone = result.contact.phoneNumber;
      await updateMe({ phone_number: phone });
      setUser((prev) => ({ ...prev, phone_number: phone }));
      try { hapticFeedbackNotificationOccurred('success'); } catch {}
    } catch {
      // User denied or not available
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
        <Spinner size="l" />
      </div>
    );
  }

  return (
    <div>
      {user && (
        <Section header="Profile">
          <Cell subtitle={`@${user.username || 'N/A'}`}>
            {user.first_name} {user.last_name || ''}
          </Cell>
          {user.phone_number ? (
            <Cell subtitle="Phone">{user.phone_number}</Cell>
          ) : (
            <Cell
              after={
                <Button size="s" mode="bezeled" onClick={handleSharePhone}>
                  Share Phone
                </Button>
              }
            >
              No phone number
            </Cell>
          )}
        </Section>
      )}

      <Section header="Order History">
        {orders.length === 0 ? (
          <Cell>No orders yet</Cell>
        ) : (
          orders.map((order) => (
            <Cell
              key={order.id}
              subtitle={`${order.total_amount.toLocaleString()} сум — ${STATUS_LABELS[order.status] || order.status}`}
              onClick={() => navigate(`/order/${order.id}`)}
            >
              {new Date(order.created_at).toLocaleDateString()}
              {order.order_number && ` #${order.order_number}`}
            </Cell>
          ))
        )}
      </Section>
    </div>
  );
}
