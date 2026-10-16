// Multilingual from day one: the TZ requires it for the final product, and
// retrofitting translation calls across a grown UI costs far more than starting
// with them. Spanish matters most in practice — it is the second language of the
// US trucking workforce.
import i18next from 'i18next'
import { initReactI18next } from 'react-i18next'

export const LANGUAGES = { en: 'English', es: 'Español', ru: 'Русский' } as const
export type Language = keyof typeof LANGUAGES

const en = {
  nav: { planner: 'Planner', history: 'History', trucks: 'Trucks', ifta: 'IFTA rates' },
  app: { title: 'Routing & Fuel Control', subtitle: 'Class 8 · United States' },
  planner: {
    origin: 'Origin',
    destination: 'Destination',
    originPlaceholder: 'Dallas, TX',
    destinationPlaceholder: 'Chicago, IL',
    truck: 'Truck',
    startFuel: 'Fuel on board at departure (gal)',
    startFuelHint: 'Leave empty for a full tank',
    corridor: 'Corridor off route (mi)',
    iftaMode: 'Fuel price basis',
    pump: 'Price on the stele',
    net: 'After IFTA tax credit',
    iftaHint:
      'The stele price is what the driver pays. The net price is what the trip really costs after the state fuel-tax credit — and it can change which stations win.',
    submit: 'Build plan',
    building: 'Building…',
    swap: 'Swap',
  },
  results: {
    heading: 'Fuel plan',
    distance: 'Distance',
    driveTime: 'Drive time',
    stops: 'Fuel stops',
    gallons: 'Gallons',
    fuelCost: 'Fuel cost',
    arrival: 'Fuel left on arrival',
    considered: '{{count}} card-accepting stations considered',
    savings: 'Saved versus no guidance',
    baseline: 'Without guidance',
    optimized: 'This plan',
    perTrip: 'on this trip',
    empty: 'Build a plan to see the recommended stops.',
    infeasible: 'No workable fuel plan',
    notTruckLegal:
      'This route was not built with a truck profile and may ignore bridge heights and weight limits.',
  },
  table: {
    seq: '#',
    station: 'Station',
    state: 'State',
    mile: 'Mile',
    detour: 'Detour',
    buy: 'Buy (gal)',
    price: 'Price/gal',
    netPrice: 'Net/gal',
    cost: 'Cost',
    arriveWith: 'Arrive (gal)',
    leaveWith: 'Leave (gal)',
  },
  ifta: {
    heading: 'Per-state mileage',
    state: 'State',
    miles: 'Miles',
    gallons: 'Gallons',
    rate: 'Tax/gal',
    owed: 'Tax owed',
    totalOwed: 'Total tax owed',
    paidAtPump: 'Paid at the pump',
    balance: 'Balance',
    balanceHint: 'Positive means the carrier still owes this much after the credit.',
  },
  history: {
    heading: 'Saved routes',
    when: 'When',
    lane: 'Lane',
    miles: 'Miles',
    cost: 'Fuel cost',
    saved: 'Saved',
    empty: 'No routes saved yet.',
    open: 'Open',
  },
  trucks: {
    heading: 'Truck profiles',
    name: 'Name',
    mpg: 'MPG',
    tank: 'Tank (gal)',
    reserve: 'Reserve',
    range: 'Range (mi)',
    usable: 'Usable (gal)',
    add: 'Add profile',
    save: 'Save',
    cancel: 'Cancel',
    delete: 'Delete',
    dimensions: 'Dimensions',
    mpgHint: 'Miles per gallon — a loaded Class 8 runs about 5.5–7.5',
  },
  iftaPage: { heading: 'IFTA fuel tax by state', state: 'State', rate: 'USD per gallon', from: 'Effective from' },
  common: {
    loading: 'Loading…',
    error: 'Something went wrong',
    retry: 'Retry',
    none: '—',
    language: 'Language',
  },
  banner: {
    modelledPrices:
      'Prices are regional averages with a modelled per-station spread, not the fuel card’s contract prices. Savings are indicative until the card portal is connected.',
    noApiKey: 'GRAPHHOPPER_API_KEY is not set, so routes cannot be built. Add it to .env and restart the API.',
  },
}

const es: typeof en = {
  nav: { planner: 'Planificador', history: 'Historial', trucks: 'Camiones', ifta: 'Tasas IFTA' },
  app: { title: 'Rutas y Control de Combustible', subtitle: 'Clase 8 · Estados Unidos' },
  planner: {
    origin: 'Origen',
    destination: 'Destino',
    originPlaceholder: 'Dallas, TX',
    destinationPlaceholder: 'Chicago, IL',
    truck: 'Camión',
    startFuel: 'Combustible al salir (gal)',
    startFuelHint: 'Vacío = tanque lleno',
    corridor: 'Desvío máximo (mi)',
    iftaMode: 'Base del precio',
    pump: 'Precio en el surtidor',
    net: 'Neto tras crédito IFTA',
    iftaHint:
      'El precio del surtidor es lo que paga el conductor. El precio neto es el costo real tras el crédito fiscal estatal, y puede cambiar qué estaciones convienen.',
    submit: 'Crear plan',
    building: 'Calculando…',
    swap: 'Invertir',
  },
  results: {
    heading: 'Plan de combustible',
    distance: 'Distancia',
    driveTime: 'Tiempo de conducción',
    stops: 'Paradas',
    gallons: 'Galones',
    fuelCost: 'Costo de combustible',
    arrival: 'Combustible al llegar',
    considered: '{{count}} estaciones con tarjeta consideradas',
    savings: 'Ahorro frente a no tener guía',
    baseline: 'Sin guía',
    optimized: 'Este plan',
    perTrip: 'en este viaje',
    empty: 'Cree un plan para ver las paradas recomendadas.',
    infeasible: 'No hay plan de combustible viable',
    notTruckLegal:
      'Esta ruta no se calculó con perfil de camión y puede ignorar límites de altura y peso.',
  },
  table: {
    seq: '#',
    station: 'Estación',
    state: 'Estado',
    mile: 'Milla',
    detour: 'Desvío',
    buy: 'Comprar (gal)',
    price: 'Precio/gal',
    netPrice: 'Neto/gal',
    cost: 'Costo',
    arriveWith: 'Llega (gal)',
    leaveWith: 'Sale (gal)',
  },
  ifta: {
    heading: 'Millas por estado',
    state: 'Estado',
    miles: 'Millas',
    gallons: 'Galones',
    rate: 'Impuesto/gal',
    owed: 'Impuesto debido',
    totalOwed: 'Total debido',
    paidAtPump: 'Pagado en el surtidor',
    balance: 'Saldo',
    balanceHint: 'Positivo significa que aún se debe esa cantidad tras el crédito.',
  },
  history: {
    heading: 'Rutas guardadas',
    when: 'Fecha',
    lane: 'Trayecto',
    miles: 'Millas',
    cost: 'Costo',
    saved: 'Ahorro',
    empty: 'Aún no hay rutas guardadas.',
    open: 'Abrir',
  },
  trucks: {
    heading: 'Perfiles de camión',
    name: 'Nombre',
    mpg: 'MPG',
    tank: 'Tanque (gal)',
    reserve: 'Reserva',
    range: 'Autonomía (mi)',
    usable: 'Utilizable (gal)',
    add: 'Añadir perfil',
    save: 'Guardar',
    cancel: 'Cancelar',
    delete: 'Eliminar',
    dimensions: 'Dimensiones',
    mpgHint: 'Millas por galón — un Clase 8 cargado hace unas 5.5–7.5',
  },
  iftaPage: { heading: 'Impuesto IFTA por estado', state: 'Estado', rate: 'USD por galón', from: 'Vigente desde' },
  common: {
    loading: 'Cargando…',
    error: 'Algo salió mal',
    retry: 'Reintentar',
    none: '—',
    language: 'Idioma',
  },
  banner: {
    modelledPrices:
      'Los precios son promedios regionales con una variación por estación modelada, no los precios de contrato de la tarjeta. El ahorro es indicativo hasta conectar el portal.',
    noApiKey: 'GRAPHHOPPER_API_KEY no está configurada, por lo que no se pueden crear rutas.',
  },
}

const ru: typeof en = {
  nav: { planner: 'Планировщик', history: 'История', trucks: 'Траки', ifta: 'Ставки IFTA' },
  app: { title: 'Маршруты и контроль топлива', subtitle: 'Class 8 · США' },
  planner: {
    origin: 'Откуда',
    destination: 'Куда',
    originPlaceholder: 'Dallas, TX',
    destinationPlaceholder: 'Chicago, IL',
    truck: 'Трак',
    startFuel: 'Топливо на старте (гал)',
    startFuelHint: 'Пусто — полный бак',
    corridor: 'Коридор от трассы (миль)',
    iftaMode: 'База цены топлива',
    pump: 'Цена на стелле',
    net: 'С вычетом IFTA',
    iftaHint:
      'Цена на стелле — то, что платит водитель. Цена с вычетом IFTA — реальная стоимость для компании, и она может изменить выбор заправок.',
    submit: 'Построить план',
    building: 'Считаю…',
    swap: 'Поменять',
  },
  results: {
    heading: 'План заправок',
    distance: 'Расстояние',
    driveTime: 'Время в пути',
    stops: 'Заправок',
    gallons: 'Галлонов',
    fuelCost: 'Стоимость топлива',
    arrival: 'Остаток по прибытии',
    considered: 'Рассмотрено заправок с картой: {{count}}',
    savings: 'Экономия против работы без подсказки',
    baseline: 'Без подсказки',
    optimized: 'Этот план',
    perTrip: 'на этом рейсе',
    empty: 'Постройте план, чтобы увидеть рекомендованные заправки.',
    infeasible: 'Рабочий план заправок невозможен',
    notTruckLegal:
      'Маршрут построен без truck-профиля и может игнорировать высоту мостов и ограничения по весу.',
  },
  table: {
    seq: '№',
    station: 'Заправка',
    state: 'Штат',
    mile: 'Миля',
    detour: 'Отклонение',
    buy: 'Залить (гал)',
    price: 'Цена/гал',
    netPrice: 'Нетто/гал',
    cost: 'Стоимость',
    arriveWith: 'Приезд (гал)',
    leaveWith: 'Отъезд (гал)',
  },
  ifta: {
    heading: 'Пробег по штатам',
    state: 'Штат',
    miles: 'Мили',
    gallons: 'Галлоны',
    rate: 'Налог/гал',
    owed: 'Налог к уплате',
    totalOwed: 'Всего к уплате',
    paidAtPump: 'Уплачено на заправках',
    balance: 'Сальдо',
    balanceHint: 'Положительное — столько ещё нужно доплатить после вычета.',
  },
  history: {
    heading: 'Сохранённые маршруты',
    when: 'Когда',
    lane: 'Направление',
    miles: 'Мили',
    cost: 'Топливо',
    saved: 'Экономия',
    empty: 'Маршрутов пока нет.',
    open: 'Открыть',
  },
  trucks: {
    heading: 'Профили траков',
    name: 'Название',
    mpg: 'MPG',
    tank: 'Бак (гал)',
    reserve: 'Резерв',
    range: 'Запас хода (миль)',
    usable: 'Доступно (гал)',
    add: 'Добавить профиль',
    save: 'Сохранить',
    cancel: 'Отмена',
    delete: 'Удалить',
    dimensions: 'Габариты',
    mpgHint: 'Миль на галлон — гружёный Class 8 идёт примерно 5.5–7.5',
  },
  iftaPage: { heading: 'Топливный налог IFTA по штатам', state: 'Штат', rate: 'USD за галлон', from: 'Действует с' },
  common: {
    loading: 'Загрузка…',
    error: 'Что-то пошло не так',
    retry: 'Повторить',
    none: '—',
    language: 'Язык',
  },
  banner: {
    modelledPrices:
      'Цены — региональные средние с модельным разбросом по заправкам, а не контрактные цены топливной карты. Экономия ориентировочная, пока не подключён кабинет провайдера.',
    noApiKey: 'GRAPHHOPPER_API_KEY не задан — маршруты построить нельзя. Добавьте ключ в .env и перезапустите API.',
  },
}

const STORAGE_KEY = 'trucking.lang'

function initialLanguage(): Language {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && saved in LANGUAGES) return saved as Language
  } catch {
    /* private mode: fall through to the browser language */
  }
  const browser = navigator.language.slice(0, 2)
  return (browser in LANGUAGES ? browser : 'en') as Language
}

void i18next.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    es: { translation: es },
    ru: { translation: ru },
  },
  lng: initialLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export function setLanguage(language: Language) {
  void i18next.changeLanguage(language)
  try {
    localStorage.setItem(STORAGE_KEY, language)
  } catch {
    /* not worth failing over */
  }
}

export default i18next
