import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../src/App';

function renderWithProviders(initialRoute = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('App', () => {
  it('renders without crashing', () => {
    renderWithProviders('/');
    expect(screen.getByText('PINITHUB')).toBeInTheDocument();
  });

  it('shows navigation links', () => {
    renderWithProviders('/');
    // Home, Protect, Vault, Investigation, History appear in the nav
    // Some also appear as card headings on the home page — use getAllByText
    expect(screen.getAllByText('Home').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Protect').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Vault').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Investigation').length).toBeGreaterThan(0);
    expect(screen.getAllByText('History').length).toBeGreaterThan(0);
  });

  it('renders the Home page by default', () => {
    renderWithProviders('/');
    expect(screen.getByText('PINITHUB Forensics')).toBeInTheDocument();
  });

  it('renders the Phase 0 notice on home page', () => {
    renderWithProviders('/');
    // Phase 0 appears in both the amber notice and the footer
    expect(screen.getAllByText(/Phase 0/).length).toBeGreaterThan(0);
  });
});
