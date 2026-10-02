export class WorkCoordinator {
    //#region Task ownership
    tasks = new Map();
    resources = new Map();
    queue = [];
    renderer = null;
    serial = 0;
    constructor(onChange = () => {}) {
        this.onChange = onChange;
    }
    get busy() {
        return this.tasks.size > 0;
    }
    requireAvailable = (resources, owner = null) => {
        const workspace = this.resources.get(`workspace`);
        if (workspace && workspace !== owner)
            throw new Error(`${workspace.label} is changing the workspace. Wait for it before starting another change.`);

        if (resources.includes(`workspace`))
            this.requireIdle(owner);

        for (const resource of resources) {
            const task = this.resources.get(resource);
            if (task && task !== owner)
                throw new Error(`${task.label} is ${task.phase === `queued` ? `queued for` : `using`} this deck. Cancel that task or wait for it before changing this deck.`);
        }
    };
    requireIdle = (owner = null) => {
        const task = [...this.tasks.values()].find(candidate => candidate !== owner);
        if (task)
            throw new Error(`${task.label} is still ${task.phase}. Cancel that task or wait for it before changing the whole workspace.`);
    };
    begin = ({label = `Working`, resources = [], background = false, signal = null, kind = `change`} = {}) => {
        if (signal?.aborted)
            throw new Error(`Task cancelled.`);

        this.requireAvailable(resources);
        const task = {id: ++this.serial, label, resources: [...new Set(resources)], background, kind,
            phase: `running`, controller: new AbortController(), progress: null};
        task.settled = new Promise(resolve => task.resolveSettled = resolve);
        task.forwardAbort = () => task.controller.abort();
        task.changed = () => this.onChange();
        task.externalSignal = signal;
        signal?.addEventListener(`abort`, task.forwardAbort, {once: true});
        task.controller.signal.addEventListener(`abort`, task.changed);
        this.tasks.set(task.id, task);
        for (const resource of task.resources) {
            this.resources.set(resource, task);
        }

        this.onChange();
        return task;
    };
    finish = task => {
        if (!this.tasks.delete(task.id))
            return;

        task.externalSignal?.removeEventListener(`abort`, task.forwardAbort);
        task.controller.signal.removeEventListener(`abort`, task.changed);
        for (const resource of task.resources) {
            if (this.resources.get(resource) === task)
                this.resources.delete(resource);
        }

        this.onChange();
        task.resolveSettled();
    };
    requireDeletable = resource => {
        const task = this.resources.get(resource);
        this.requireAvailable([resource],task?.kind === `generation` ? task : null);
    };
    cancelGeneration = resource => {
        this.requireDeletable(resource);
        const task = this.resources.get(resource);
        if (!task)
            return Promise.resolve();

        task.controller.abort();
        return task.settled;
    };
    update = (task, progress) => {
        if (!this.tasks.has(task.id))
            return;

        task.progress = progress;
        this.onChange();
    };
    visible = () => [...this.tasks.values()].filter(task => task.progress && task.phase === `running`)
        .sort((left, right) => Number(left.background) - Number(right.background) || right.id - left.id)[0] || null;
    //#endregion

    //#region One native renderer with cancellable queued work
    render = (operation, options = {}) => {
        const task = this.begin({...options, background: options.background ?? true});
        task.phase = `queued`;
        return new Promise((resolve, reject) => {
            const entry = {task, operation, resolve, reject};
            entry.cancelQueued = () => {
                if (task.phase !== `queued`)
                    return;

                this.queue = this.queue.filter(candidate => candidate !== entry);
                this.finish(task);
                reject(new Error(`Queued task cancelled.`));
            };
            task.controller.signal.addEventListener(`abort`, entry.cancelQueued, {once: true});
            this.queue.push(entry);
            this.onChange();
            this.next();
        });
    };
    next = () => {
        if (this.renderer || !this.queue.length)
            return;

        //Explicit foreground previews get a turn before queued deck generation.
        this.queue.sort((left, right) => Number(left.task.background) - Number(right.task.background) || left.task.id - right.task.id);
        const entry = this.queue.shift();
        this.renderer = entry.task;
        entry.task.phase = `running`;
        entry.task.controller.signal.removeEventListener(`abort`, entry.cancelQueued);
        this.onChange();
        Promise.resolve().then(() => {
            if (entry.task.controller.signal.aborted)
                throw new Error(`Task cancelled.`);

            return entry.operation(entry.task);
        }).then(result => this.complete(entry, result), error => this.complete(entry, null, error));
    };
    complete = (entry, result, error = null) => {
        this.finish(entry.task);
        this.renderer = null;
        this.next();
        if (error)
            entry.reject(error);
        else
            entry.resolve(result);
    };
    //#endregion
}