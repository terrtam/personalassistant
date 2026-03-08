import { Link2 } from 'lucide-react'

export function MessageItem({ item, versionIndex, onPrev, onNext }) {
  const version = item.versions[versionIndex] ?? item.versions[0]

  return (
    <article className={`message ${item.from === 'user' ? 'from-user' : 'from-assistant'}`}>
      <div className="bubble">
        {item.model ? <p className="group-label">Model: {item.model}</p> : null}
        {item.sources?.length ? (
          <details className="expander">
            <summary>Sources ({item.sources.length})</summary>
            <ul className="source-list">
              {item.sources.map((source, index) => (
                <li key={`${source.title}-${index}`}>
                  <Link2 size={12} />
                  {source.href ? (
                    <a href={source.href} rel="noreferrer" target="_blank">
                      {source.title}
                    </a>
                  ) : (
                    <span>{source.title}</span>
                  )}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
        <p className="message-text">{version.content}</p>
      </div>
      {item.versions.length > 1 ? (
        <div className="branch-controls">
          <button className="btn btn-ghost" onClick={onPrev} type="button">
            Prev
          </button>
          <span>
            {versionIndex + 1}/{item.versions.length}
          </span>
          <button className="btn btn-ghost" onClick={onNext} type="button">
            Next
          </button>
        </div>
      ) : null}
    </article>
  )
}
