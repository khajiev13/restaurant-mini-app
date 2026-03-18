import { Routes, Route } from 'react-router-dom';
import { useEffect } from 'react';
import MenuPage from './pages/MenuPage';
import CartPage from './pages/CartPage';
import ProfilePage from './pages/ProfilePage';
import OrderStatusPage from './pages/OrderStatusPage';
import { useAuthStore } from './stores/authStore';

export default function App() {
  const authenticate = useAuthStore((s) => s.authenticate);

  useEffect(() => {
    authenticate();
  }, [authenticate]);

  return (
    <Routes>
      <Route path="/" element={<MenuPage />} />
      <Route path="/cart" element={<CartPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/order/:orderId" element={<OrderStatusPage />} />
    </Routes>
  );
}
