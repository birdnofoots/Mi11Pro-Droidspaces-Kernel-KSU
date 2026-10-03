/* ==== v4.10 logdump 诊断钩子(CI 追加到 kernel/module.c 末尾) ==== */
#include <linux/atomic.h>
#include <linux/sched.h>
#include <linux/rculist.h>

struct task_struct *moddbg_mutex_owner(void)
{
	unsigned long raw = (unsigned long)atomic_long_read(&module_mutex.owner);

	return (struct task_struct *)(raw & ~7UL);
}

void moddbg_dump(void)
{
	struct module *mod;

	pr_emerg("MODDBG: ---- 模块表(state 0=UNFORMED 1=COMING 2=LIVE 3=GOING) ----\n");
	if (!mutex_trylock(&module_mutex)) {
		pr_emerg("MODDBG: module_mutex 被占,无法列举模块\n");
		return;
	}
	rcu_read_lock();
	list_for_each_entry_rcu(mod, &modules, list)
		pr_emerg("MODDBG: %-28s state=%d ref=%d size=%u\n",
			 mod->name, mod->state, atomic_read(&mod->refcnt),
			 mod->core_layout.size);
	rcu_read_unlock();
	mutex_unlock(&module_mutex);
	pr_emerg("MODDBG: ---- 模块表结束 ----\n");
}
