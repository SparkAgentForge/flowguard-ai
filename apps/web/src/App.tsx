import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from './components/AppShell'
import { DashboardPage } from './pages/DashboardPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import './styles.css'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="sops" element={<PlaceholderPage section="SOP 中心" />} />
          <Route path="work-orders" element={<PlaceholderPage section="工单中心" />} />
          <Route path="exceptions" element={<PlaceholderPage section="异常处置" />} />
          <Route path="reports" element={<PlaceholderPage section="证据归档" />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
