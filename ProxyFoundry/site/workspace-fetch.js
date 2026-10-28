//Browser workspaces talk to their engine directly; local servers use HTTP.
export function workspaceFetch(path,options) {
    if(window.__pfWorkspaceFetch)
        return window.__pfWorkspaceFetch(path,options);

    return fetch(path,options);
}