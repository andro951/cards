export class RequestQueue {
    pending = [];
    running = false;
    timer = null;
    serial = 0;
    //Each operation owns the Python runtime until its response and save finish.
    enqueue = (operation, priority = 0) => new Promise((resolve, reject) => {
        this.pending.push({operation, priority, serial: this.serial++, resolve, reject});
        this.schedule();
    });
    schedule = () => {
        if (this.running || this.timer !== null || !this.pending.length)
            return;
        //A real task turn lets worker messages arrive before choosing the next request.
        this.timer = setTimeout(this.pump, 0);
    };
    rank = task => typeof task.priority === `function` ? task.priority() : task.priority;
    pump = async () => {
        this.timer = null;
        this.pending.sort((left, right) => this.rank(left) - this.rank(right) || left.serial - right.serial);
        const task = this.pending.shift();
        if (!task)
            return;

        this.running = true;
        try { task.resolve(await task.operation()); }
        catch (error) { task.reject(error); }
        finally { this.running = false; this.schedule(); }
    };
}

export function requestPriority({url = ''}) {
    if (typeof url !== 'string')
        return 0;

    if (/^\/(runtime|js|img|fonts|css|creator)\//.test(url) || url.startsWith('/api/render-sessions'))
        return 2;
    if (url.startsWith('/api/assets/'))
        return 1;
    if (['/api/render-diagnostic', '/api/client-error'].includes(url))
        return 3;
    return 0;
}