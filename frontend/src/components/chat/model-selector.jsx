import { useMemo, useState } from 'react'

const providers = ['OpenAI', 'Anthropic', 'Google']

export function ModelSelector({ model, models, onChange }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')

  const selected = useMemo(() => models.find((entry) => entry.id === model), [model, models])
  const grouped = useMemo(() => {
    const query = search.toLowerCase().trim()
    const filtered = query
      ? models.filter((entry) => `${entry.name} ${entry.provider}`.toLowerCase().includes(query))
      : models
    return providers.map((provider) => ({
      provider,
      entries: filtered.filter((entry) => entry.provider === provider),
    }))
  }, [models, search])

  return (
    <div className="model-selector">
      <button className="btn btn-secondary" onClick={() => setOpen((value) => !value)} type="button">
        <span className="provider-dot" />
        {selected?.name ?? 'Select model'}
      </button>
      {open ? (
        <div className="popover">
          <input
            className="input"
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search models..."
            value={search}
          />
          <div className="model-list">
          {grouped.map((group) => (
            <div key={group.provider}>
              <p className="group-label">{group.provider}</p>
              {group.entries.length ? (
                group.entries.map((entry) => (
                  <button
                    className="model-item"
                    key={entry.id}
                    onClick={() => {
                      onChange(entry.id)
                      setOpen(false)
                    }}
                    type="button"
                  >
                    <span>{entry.name}</span>
                    {entry.id === model ? <span>✓</span> : <span className="placeholder">•</span>}
                  </button>
                ))
              ) : (
                <p className="empty-models">No models found.</p>
              )}
            </div>
          ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}
