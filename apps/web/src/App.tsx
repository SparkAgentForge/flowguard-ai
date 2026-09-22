import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from './components/AppShell'
import { DashboardPage } from './pages/DashboardPage'
import { ExceptionsPage } from './pages/ExceptionsPage'
import { ReportsPage } from './pages/ReportsPage'
import { SopWorkspacePage } from './pages/SopWorkspacePage'
import { WorkOrdersPage } from './pages/WorkOrdersPage'
import './styles.css'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="sops" element={<SopWorkspacePage />} />
          <Route path="work-orders" element={<WorkOrdersPage />} />
          <Route path="exceptions" element={<ExceptionsPage />} />
          <Route path="reports" element={<ReportsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
