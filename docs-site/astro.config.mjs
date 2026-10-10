// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://qwik.ragilhadi.com',
  integrations: [
    sitemap(),
    starlight({
      title: 'Docs | qwik',
      description:
        'A friendly CLI alias manager. Create, manage, and run shell aliases from a single interface — bash, zsh, fish, PowerShell, cmd, Nushell, and Xonsh.',
      favicon: '/favicon.svg',
      head: [
        { tag: 'meta', attrs: { name: 'theme-color', content: '#1a1a2e' } },
        { tag: 'meta', attrs: { name: 'author', content: 'Ragil Ilman' } },
        { tag: 'link', attrs: { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' } },
        { tag: 'meta', attrs: { property: 'og:type', content: 'website' } },
        { tag: 'meta', attrs: { property: 'og:site_name', content: 'qwik' } },
        { tag: 'meta', attrs: { property: 'og:image', content: 'https://qwik.ragilhadi.com/favicon.svg' } },
        { tag: 'meta', attrs: { property: 'og:image:width', content: '32' } },
        { tag: 'meta', attrs: { property: 'og:image:height', content: '32' } },
        { tag: 'meta', attrs: { name: 'twitter:card', content: 'summary' } },
        { tag: 'meta', attrs: { name: 'twitter:title', content: 'qwik — A Friendly CLI Alias Manager' } },
        { tag: 'meta', attrs: { name: 'twitter:image', content: 'https://qwik.ragilhadi.com/favicon.svg' } },
      ],
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/ragilhadi/qwik',
        },
        {
          icon: 'seti:python',
          label: 'PyPI',
          href: 'https://pypi.org/project/qwik/',
        },
      ],
      editLink: {
        baseUrl: 'https://github.com/ragilhadi/qwik/edit/master/docs-site/',
      },
      sidebar: [
        {
          label: 'Start Here',
          items: [
            { label: 'Introduction', slug: 'start-here/introduction' },
            { label: 'Installation', slug: 'start-here/installation' },
            { label: 'Quick Start', slug: 'start-here/quick-start' },
          ],
        },
        {
          label: 'Guides',
          items: [
            { label: 'Alias Templates & Arguments', slug: 'guides/alias-templates' },
            { label: 'Shell Integration', slug: 'guides/shell-integration' },
            { label: 'Organizing Aliases', slug: 'guides/organizing' },
            { label: 'Sharing & Syncing', slug: 'guides/sharing' },
            { label: 'Conflict Detection', slug: 'guides/conflicts' },
            { label: 'Shell Completions', slug: 'guides/completions' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'Commands', slug: 'reference/commands' },
            { label: 'Shell Quoting & Escaping', slug: 'reference/shell-quoting' },
            { label: 'Store & Backups', slug: 'reference/store' },
            { label: 'Environment Variables', slug: 'reference/environment' },
            { label: 'Plugin System', slug: 'reference/plugins' },
            { label: 'Troubleshooting', slug: 'reference/troubleshooting' },
          ],
        },
      ],
    }),
  ],
});
