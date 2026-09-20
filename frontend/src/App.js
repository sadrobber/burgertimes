import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";

import { I18nProvider } from "@/context/I18nContext.jsx";
import { CartProvider } from "@/context/CartContext.jsx";
import { AdminAuthProvider, useAdminAuth } from "@/context/AdminAuthContext.jsx";
import { KitchenAuthProvider, useKitchenAuth } from "@/context/KitchenAuthContext.jsx";
import { TabletAuthProvider, useTabletAuth } from "@/context/TabletAuthContext.jsx";

import Home from "@/pages/Home.jsx";
import Menu from "@/pages/Menu.jsx";
import Cart from "@/pages/Cart.jsx";
import Checkout from "@/pages/Checkout.jsx";
import OrderSuccess from "@/pages/OrderSuccess.jsx";

import AdminLogin from "@/pages/admin/AdminLogin.jsx";
import AdminLayout from "@/pages/admin/AdminLayout.jsx";
import Dashboard from "@/pages/admin/Dashboard.jsx";
import OrdersAdmin from "@/pages/admin/OrdersAdmin.jsx";
import MenuAdmin from "@/pages/admin/MenuAdmin.jsx";
import CategoriesAdmin from "@/pages/admin/CategoriesAdmin.jsx";
import BurgerBuilderAdmin from "@/pages/admin/BurgerBuilderAdmin.jsx";
import SaucesAdmin from "@/pages/admin/SaucesAdmin.jsx";
import CouponsAdmin from "@/pages/admin/CouponsAdmin.jsx";
import ReviewsAdmin from "@/pages/admin/ReviewsAdmin.jsx";
import SettingsAdmin from "@/pages/admin/SettingsAdmin.jsx";
import DeliveryStatsAdmin from "@/pages/admin/DeliveryStatsAdmin.jsx";
import TabletStaffAdmin from "@/pages/admin/TabletStaffAdmin.jsx";
import ScrollToTop from "@/components/ScrollToTop.jsx";

import KitchenLogin from "@/pages/kitchen/KitchenLogin.jsx";
import Kitchen from "@/pages/kitchen/Kitchen.jsx";
import TabletLogin from "@/pages/tablet/TabletLogin.jsx";
import TabletOrder from "@/pages/tablet/TabletOrder.jsx";

function AdminGuard({ children }) {
  const { status } = useAdminAuth();
  if (status !== "authenticated") return <Navigate to="/admin/login" replace />;
  return children;
}

function KitchenGuard({ children }) {
  const { status } = useKitchenAuth();
  if (status !== "authenticated") return <Navigate to="/kitchen/login" replace />;
  return children;
}

function TabletGuard({ children }) {
  const { status } = useTabletAuth();
  if (status !== "authenticated") return <Navigate to="/tablet/login" replace />;
  return children;
}

function App() {
  return (
    <I18nProvider>
      <AdminAuthProvider>
        <KitchenAuthProvider>
          <TabletAuthProvider>
            <CartProvider>
            <BrowserRouter>
              <ScrollToTop />
              <Toaster
                richColors
                theme="dark"
                toastOptions={{
                  style: {
                    background: "#141414",
                    border: "2px solid #262626",
                    color: "#F5F1E8",
                    borderRadius: 0,
                    fontFamily: "Outfit, sans-serif",
                  },
                }}
              />
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/menu" element={<Menu />} />
                <Route path="/cart" element={<Cart />} />
                <Route path="/checkout" element={<Checkout />} />
                <Route path="/order/success" element={<OrderSuccess />} />
                <Route path="/admin/login" element={<AdminLogin />} />
                <Route
                  path="/admin"
                  element={
                    <AdminGuard>
                      <AdminLayout />
                    </AdminGuard>
                  }
                >
                  <Route index element={<Dashboard />} />
                  <Route path="orders" element={<OrdersAdmin />} />
                  <Route path="menu" element={<MenuAdmin />} />
                  <Route path="categories" element={<CategoriesAdmin />} />
                  <Route path="burger" element={<BurgerBuilderAdmin />} />
                  <Route path="sauces" element={<SaucesAdmin />} />
                  <Route path="coupons" element={<CouponsAdmin />} />
                  <Route path="tablet-staff" element={<TabletStaffAdmin />} />
                  <Route path="reviews" element={<ReviewsAdmin />} />
                  <Route path="stats/delivery" element={<DeliveryStatsAdmin />} />
                  <Route path="settings" element={<SettingsAdmin />} />
                </Route>
                <Route path="/kitchen/login" element={<KitchenLogin />} />
                <Route
                  path="/kitchen"
                  element={
                    <KitchenGuard>
                      <Kitchen />
                    </KitchenGuard>
                  }
                />
                <Route path="/tablet/login" element={<TabletLogin />} />
                <Route
                  path="/tablet"
                  element={
                    <TabletGuard>
                      <TabletOrder />
                    </TabletGuard>
                  }
                />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </BrowserRouter>
            </CartProvider>
          </TabletAuthProvider>
        </KitchenAuthProvider>
      </AdminAuthProvider>
    </I18nProvider>
  );
}

export default App;
