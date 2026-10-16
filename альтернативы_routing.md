# Альтернативы для truck-маршрутизации

Обзор состояния рынка на сентябрь 2026 года. Составлен после того, как выяснилось, что
профиль `truck` недоступен на текущем ключе GraphHopper: аккаунт принимает только
`car`, `bike` и `foot`, truck-маршрутизация вынесена на платные тарифы.

Ссылки на источники — в конце документа.

## Скрытая проблема: мили — это деньги

PC*Miler practical miles — не просто маршрут, а **отраслевой стандарт расчётов** в США.
По ним брокеры выставляют rate confirmation, по ним считается оплата водителю, на них
ссылаются страховые и брокеры в спорах, и их же используют в аудитах IFTA. Разрыв между
PC*Miler practical и другими способами счёта на одном и том же плече достигает **3–5%**.

Для проекта это прямое следствие: если CRM и факторинговая компания оперируют милями
PC*Miler, а система считает по GraphHopper или HERE, расхождение вылезет именно в
деньгах — в счетах и в отчётности.

**Вопрос заказчику до выбора API: в каких милях ему выставляют rate confirmation?**

## Коммерческие API

| Сервис | Truck-возможности | Вход | Замечание |
|---|---|---|---|
| **HERE Routing v8** | Отдельный commercial vehicle profile, 30+ ограничений: габариты, вес, оси, тоннельные категории, hazmat, эко-зоны | Limited Plan — 1000 запросов/день бесплатно; Base Plan — по карте, pay-as-you-grow | Вес задаётся **по группам осей** (single/tandem/triple/quad/quint) — это то, как написаны US bridge formula и лимиты штатов. Цены выросли ~6% с апреля 2026 |
| **Trimble Maps / PC\*Miler** | Габариты, вес, клиренс мостов, hazmat + 30 лет собственных данных об ограничениях | Trial-ключ на 30 дней; коммерческие планы от ~$200/мес, PC\*Miler Web от $84.99/мес за пользователя | Тот самый отраслевой стандарт. Даёт юридическую защиту в спорах и совпадение с биллингом |
| **Google Routes API — Large Vehicle Routing** | Высота, вес, длина, ширина, число осей, hazmat; обходит низкие мосты | **По заявке**: «available to a limited set of customers, contact us» | Запущен в августе 2026, GA в 48 континентальных штатах. Требует `TRAFFIC_AWARE_OPTIMAL` (дорогой тариф). Прямо оговаривает: маршруты **не гарантированно пригодны** для ТС и могут «best effort» игнорировать ограничения; платных truck-толлов нет |
| **TomTom** | Truck-маршрутизация с габаритами и hazmat | Freemium | Вес оси — **один скаляр** вместо групп осей, для американских лимитов это потеря информации. Тарифы меняются с 1 июля 2026 |
| **Azure Maps Route Directions** | Коммерческий транспорт: габариты, вес, hazmat, высоты мостов и тоннелей | Azure-подписка | Сюда мигрирует Bing Maps Truck Route API (для enterprise работает до 30 июня 2028) |

## Open source и self-hosted

**Valhalla** — сильнейший из открытых для грузовиков: truck costing читает теги
`maxweight`, `maxheight`, `hazmat` прямо из OSM и выставляет их параметрами запроса.
Есть managed-вариант — **Stadia Maps** (хостинг Valhalla с truck-профилем, кредитная
тарификация), если не хотите держать инфраструктуру.

**GraphHopper self-hosted** — то, что используется сейчас, но без ограничений облачного
тарифа: truck-профиль настраивается через custom model, работает на скромном железе.

**openrouteservice** — профиль `driving-hgv`, построен поверх GraphHopper, есть
бесплатное API с квотами.

**OSRM** — truck-профиля по сути нет, ограничения по габаритам не поддерживает. Не вариант.

Общая оговорка ко всем открытым движкам: они **truck-образные, но не юридически
защищённые**. Качество ограничений упирается в разметку OSM, а низкие мосты в США
размечены далеко не полностью. Именно за это платят деньги HERE и Trimble.

## Рекомендация для этого проекта

**Сейчас, чтобы снять блокер:** подключить HERE вторым `RouteProvider`. Truck-профиль
доступен без заявки и без апгрейда, вес по группам осей — ровно то, что нужно для США,
а 1000 запросов в день с запасом покрывают демо и разработку. Это один новый подкласс
и запись в конфиге — ядро оптимизации не трогается вообще.

**Перед продакшеном:** запросить прайс у Trimble Maps. Если заказчику выставляют счета
в милях PC*Miler, это не вопрос удобства, а вопрос совпадения цифр системы с деньгами,
которые он получает от брокеров и факторинга.

**Google LVR** стоит запросить параллельно — он новый и может оказаться дешевле, но с
оговоркой «маршрут не гарантированно пригоден для ТС» он не заменяет коммерческие данные
там, где речь о спорах и ответственности.

**Self-hosted Valhalla или GraphHopper** — как способ сбить стоимость при масштабировании
в SaaS, но не как единственный источник правды о легальности маршрута.

## Как это ложится на код

Смена провайдера — это новый подкласс `RouteProvider`
(`backend/app/services/routing/base.py`) и значение в конфиге. Всё, что ниже по течению —
коридорный запрос, оптимизатор, IFTA, сохранение истории — зависит только от
`RouteResult` и не меняется. Флаг `truck_legal` в ответе API показывает, построен ли
маршрут truck-профилем; сейчас он `false` на каждом маршруте.

## Источники

- [Large vehicle routing overview — Google Routes API](https://developers.google.com/maps/documentation/routes/lvr)
- [Introducing Large Vehicle Routing — Google Maps Platform](https://mapsplatform.google.com/resources/blog/introducing-large-vehicle-routing-address-the-unique-logistics-needs-of-large-vehicle-fleets/)
- [Truck Routing — Trimble Maps Development Platform](https://developer.trimblemaps.com/features-guide/truck-routing/)
- [PC*Miler — Trimble Transportation](https://transportation.trimble.com/en/solutions/mapping-and-routing/pcmiler)
- [HERE vs TomTom — Logistics Routing Comparison 2026](https://placematic.com/compare/here-vs-tomtom/)
- [HERE Pricing Plans — Base Plan restrictions](https://www.here.com/get-started/pricing/base-plan-restrictions)
- [Migrate Bing Maps Calculate a Truck Route to Azure Maps — Microsoft Learn](https://learn.microsoft.com/en-us/azure/azure-maps/migrate-calculate-truck-route)
- [Valhalla — open source routing engine](https://github.com/valhalla/valhalla)
- [Routing APIs — Stadia Maps Documentation](https://docs.stadiamaps.com/routing/)
- [Rate Confirmation Errors Freight Brokers Miss — Laneproof](https://www.laneproof.com/blog/rate-confirmation-errors-freight-brokers-miss)
