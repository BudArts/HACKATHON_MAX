import { Link, useParams } from 'react-router-dom';

import { Alert, Card, ScreenLoader } from '../components/ui';
import { api } from '../lib/api';
import { useQuery } from '../lib/useQuery';
import type { PolicyView } from '../types';

export function LegalListPage(): JSX.Element {
  const query = useQuery<PolicyView[]>(() => api.get<PolicyView[]>('/legal'), 'legal');

  if (query.loading) return <ScreenLoader />;
  if (query.error) return <Alert tone="danger">{query.error}</Alert>;

  return (
    <div className="stack">
      <Alert tone="info">
        Действующие редакции документов. Факт ознакомления и согласия фиксируется с указанием редакции.
      </Alert>
      <div className="list">
        {(query.data ?? []).map((document) => (
          <Link className="list-item" to={`/legal/${document.code}`} key={document.code}>
            <div className="list-item__title">{document.title}</div>
            <div className="list-item__meta">
              <span>Редакция {document.version}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function LegalDocumentPage(): JSX.Element {
  const { code = '' } = useParams();
  const query = useQuery<PolicyView>(() => api.get<PolicyView>(`/legal/${code}`), `legal:${code}`);

  if (query.loading) return <ScreenLoader />;
  if (query.error || !query.data) return <Alert tone="danger">Документ не найден</Alert>;

  return (
    <Card title={query.data.title} hint={`Редакция ${query.data.version}`}>
      <LegalText source={query.data.body} />
    </Card>
  );
}

export function LegalText({ source }: { source: string }): JSX.Element {
  const blocks = source.split(/\n{2,}/);
  return (
    <div className="legal">
      {blocks.map((block, index) => {
        const text = block.trim();
        if (!text) return null;
        if (text.startsWith('## ')) return <h2 key={index}>{text.slice(3)}</h2>;
        if (text.startsWith('# ')) return <h1 key={index}>{text.slice(2)}</h1>;
        if (text.startsWith('- ')) {
          return (
            <ul key={index}>
              {text.split('\n').map((line) => (
                <li key={line}>{line.replace(/^- /, '')}</li>
              ))}
            </ul>
          );
        }
        return <p key={index}>{text}</p>;
      })}
    </div>
  );
}
