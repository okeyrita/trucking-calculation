import { NavLink, Route, Routes } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LANGUAGES, setLanguage, type Language } from './i18n'
import { History } from './pages/History'
import { IftaRates } from './pages/IftaRates'
import { Planner } from './pages/Planner'
import { RouteDetail } from './pages/RouteDetail'
import { Trucks } from './pages/Trucks'

export function App() {
  const { t, i18n } = useTranslation()

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <strong>{t('app.title')}</strong>
          <small>{t('app.subtitle')}</small>
        </div>

        <nav>
          <NavLink to="/" end>
            {t('nav.planner')}
          </NavLink>
          <NavLink to="/history">{t('nav.history')}</NavLink>
          <NavLink to="/trucks">{t('nav.trucks')}</NavLink>
          <NavLink to="/ifta">{t('nav.ifta')}</NavLink>
        </nav>

        <label className="lang">
          <span className="sr-only">{t('common.language')}</span>
          <select
            value={i18n.language.slice(0, 2)}
            onChange={(event) => setLanguage(event.target.value as Language)}
          >
            {Object.entries(LANGUAGES).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<Planner />} />
          <Route path="/history" element={<History />} />
          <Route path="/routes/:routeId" element={<RouteDetail />} />
          <Route path="/trucks" element={<Trucks />} />
          <Route path="/ifta" element={<IftaRates />} />
        </Routes>
      </main>
    </>
  )
}
