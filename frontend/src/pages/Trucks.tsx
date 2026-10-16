import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api, ApiError } from '../api'
import { makeNumber } from '../format'
import type { TruckProfile } from '../types'

const BLANK = {
  name: '',
  mpg: 6.5,
  tank_gallons: 200,
  reserve_fraction: 0.15,
  height_m: 4.11,
  width_m: 2.59,
  length_m: 22,
  weight_kg: 36287,
  axles: 5,
}

export function Trucks() {
  const { t, i18n } = useTranslation()
  const numbers = makeNumber(i18n.language)
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<typeof BLANK | null>(null)

  const trucks = useQuery({ queryKey: ['trucks'], queryFn: api.trucks })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['trucks'] })
  const create = useMutation({
    mutationFn: (payload: Partial<TruckProfile>) => api.createTruck(payload),
    onSuccess: () => {
      setDraft(null)
      void invalidate()
    },
  })
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteTruck(id),
    onSuccess: invalidate,
  })

  return (
    <section className="panel">
      <h2>{t('trucks.heading')}</h2>

      {(create.isError || remove.isError) && (
        <p className="banner banner-error">
          {(create.error ?? remove.error) instanceof ApiError
            ? (create.error ?? remove.error)!.message
            : t('common.error')}
        </p>
      )}

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t('trucks.name')}</th>
              <th className="num">{t('trucks.mpg')}</th>
              <th className="num">{t('trucks.tank')}</th>
              <th className="num">{t('trucks.reserve')}</th>
              <th className="num">{t('trucks.usable')}</th>
              <th className="num">{t('trucks.range')}</th>
              <th>{t('trucks.dimensions')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {trucks.data?.map((truck) => (
              <tr key={truck.id}>
                <td className="strong">{truck.name}</td>
                <td className="num">{truck.mpg}</td>
                <td className="num">{truck.tank_gallons}</td>
                <td className="num">{(truck.reserve_fraction * 100).toFixed(0)}%</td>
                <td className="num">{truck.usable_gallons.toFixed(0)}</td>
                <td className="num strong">{numbers.format(truck.range_miles)}</td>
                <td className="muted">
                  {truck.height_m} × {truck.width_m} × {truck.length_m} m ·{' '}
                  {numbers.format(truck.weight_kg)} kg · {truck.axles} axles
                </td>
                <td>
                  <button
                    type="button"
                    className="ghost danger"
                    onClick={() => remove.mutate(truck.id)}
                  >
                    {t('trucks.delete')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {draft === null ? (
        <button type="button" className="primary" onClick={() => setDraft({ ...BLANK })}>
          {t('trucks.add')}
        </button>
      ) : (
        <form
          className="form"
          onSubmit={(event) => {
            event.preventDefault()
            create.mutate(draft)
          }}
        >
          <div className="field grow">
            <label htmlFor="name">{t('trucks.name')}</label>
            <input
              id="name"
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              required
            />
          </div>
          <div className="field narrow">
            <label htmlFor="mpg">{t('trucks.mpg')}</label>
            <input
              id="mpg"
              type="number"
              step={0.1}
              min={0.1}
              value={draft.mpg}
              onChange={(event) => setDraft({ ...draft, mpg: Number(event.target.value) })}
            />
          </div>
          <div className="field narrow">
            <label htmlFor="tank">{t('trucks.tank')}</label>
            <input
              id="tank"
              type="number"
              step={5}
              min={1}
              value={draft.tank_gallons}
              onChange={(event) => setDraft({ ...draft, tank_gallons: Number(event.target.value) })}
            />
          </div>
          <div className="field narrow">
            <label htmlFor="reserve">{t('trucks.reserve')}</label>
            <input
              id="reserve"
              type="number"
              step={0.05}
              min={0}
              max={0.9}
              value={draft.reserve_fraction}
              onChange={(event) =>
                setDraft({ ...draft, reserve_fraction: Number(event.target.value) })
              }
            />
          </div>
          <button type="submit" className="primary" disabled={create.isPending}>
            {t('trucks.save')}
          </button>
          <button type="button" className="ghost" onClick={() => setDraft(null)}>
            {t('trucks.cancel')}
          </button>
          <p className="hint">{t('trucks.mpgHint')}</p>
        </form>
      )}
    </section>
  )
}
