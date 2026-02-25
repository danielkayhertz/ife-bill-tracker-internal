export default {
  async fetch(request, env) {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, PUT',
          'Access-Control-Allow-Headers': 'Content-Type',
        }
      });
    }

    // Proxy path: /github/repos/OWNER/REPO/contents/PATH
    const url = new URL(request.url);
    const githubUrl = 'https://api.github.com' + url.pathname.replace('/github', '') + url.search;

    const resp = await fetch(githubUrl, {
      method: request.method,
      headers: {
        Authorization: `token ${env.GITHUB_TOKEN}`,
        Accept: 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
        'User-Agent': 'ife-bill-tracker-proxy',
      },
      body: request.method === 'PUT' ? request.body : undefined,
    });

    const body = await resp.text();
    return new Response(body, {
      status: resp.status,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      }
    });
  }
};
