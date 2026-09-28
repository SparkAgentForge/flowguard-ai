import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AuditPage } from './pages/AuditPage'
import { ExceptionPage } from './pages/ExceptionPage'
import { LandingPage } from './pages/LandingPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ReportPage } from './pages/ReportPage'
import { SopPage } from './pages/SopPage'
import './styles.css'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/sop/:versionId" element={<SopPage />} />
        <Route path="/audit/:workOrderId/:auditId" element={<AuditPage />} />
        <Route path="/exception/:exceptionId" element={<ExceptionPage />} />
        <Route path="/report/:workOrderId" element={<ReportPage />} />
        <Route path="/404" element={<NotFoundPage />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
