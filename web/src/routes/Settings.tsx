import { Link } from 'react-router-dom';

import { Topbar } from '../components/AppShell';
import { Card, EmptyNote, Page, PageHeader, Pill, Row, Section } from '../components/ui';
import { useConnections } from '../hooks/useConnections';

export default function Settings() {
  const { data: conns } = useConnections();

  return (
    <>
      <Topbar title="Settings" />
      <Page>
        <PageHeader title="Settings" sub="Applies to every knowledge base in this workspace." />
        <Section title="Model providers" action={<Link to="/keys" className="text-[13px] font-medium">Manage</Link>}>
          {conns && conns.length === 0 && (
            <EmptyNote>
              No providers yet. <Link to="/keys">Add an API Base and key</Link> on the API keys screen.
            </EmptyNote>
          )}
          {conns && conns.length > 0 && (
            <Card>
              {conns.map((c) => (
                <Row key={c.id} title={c.name} sub={<span className="font-mono">{c.api_base}</span>}>
                  <Pill tone="ok">Connected · {c.models.length} models</Pill>
                </Row>
              ))}
            </Card>
          )}
        </Section>
        <Section title="Embeddings">
          <Card>
            <Row title="Embedding model" sub="Changing this re-indexes every document.">
              <span className="font-mono text-[13px] text-muted">BAAI/bge-small-en-v1.5 · Local</span>
            </Row>
            <Row title="Vector store" sub="Stored on this server.">
              <span className="font-mono text-[13px] text-muted">Chroma · 384 dims</span>
            </Row>
          </Card>
        </Section>
        <Section title="Chunking and retrieval">
          <EmptyNote>Chunk size, overlap, top-k, hybrid search and reranking controls arrive with the ingest pipeline.</EmptyNote>
        </Section>
      </Page>
    </>
  );
}
