"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/dashboard/shell";
import { ItemDialog } from "@/components/menu/item-dialog";
import { SortableList } from "@/components/sortable-list";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { VegMarker } from "@/components/veg-marker";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatPaise } from "@/lib/money";
import type { CategoryOut, ItemOut } from "@/lib/types";
import { cn } from "@/lib/utils";

const UNCATEGORIZED = "uncategorized";

type Section = { id: string; category: CategoryOut | null; items: ItemOut[] };

function useMenu() {
  const categories = useQuery({
    queryKey: ["menu", "categories"],
    queryFn: () => api<CategoryOut[]>("/menu/categories"),
  });
  const items = useQuery({
    queryKey: ["menu", "items"],
    queryFn: () => api<ItemOut[]>("/menu/items"),
  });
  return { categories, items };
}

function ItemRow({
  item,
  handle,
  canEdit,
  onEdit,
  onToggle,
  onDelete,
}: {
  item: ItemOut;
  handle: React.ReactNode;
  canEdit: boolean;
  onEdit: () => void;
  onToggle: (available: boolean) => void;
  onDelete: () => void;
}) {
  return (
    <div className="bg-card flex items-center gap-3 border-b px-2 py-2 last:border-0">
      {handle}
      <div className="bg-muted size-12 shrink-0 overflow-hidden rounded-md">
        {item.image_url && (
          // eslint-disable-next-line @next/next/no-img-element -- already resized server-side
          <img src={item.image_url} alt="" className="size-full object-cover" />
        )}
      </div>
      <div className={cn("min-w-0 flex-1", !item.is_available && "opacity-60")}>
        <div className="flex items-center gap-2">
          <VegMarker isVeg={item.is_veg} />
          <span className="truncate font-medium">{item.name}</span>
        </div>
        <div className="text-muted-foreground mt-0.5 flex flex-wrap items-center gap-1.5 text-sm">
          <span>{formatPaise(item.price_paise)}</span>
          {item.tags.map((t) => (
            <Badge key={t} variant="secondary" className="font-normal">
              {t}
            </Badge>
          ))}
        </div>
      </div>
      {canEdit ? (
        <>
          <Switch
            checked={item.is_available}
            onCheckedChange={onToggle}
            aria-label={`${item.name} available`}
          />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label={`Actions for ${item.name}`}>
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={onEdit}>
                <Pencil /> Edit
              </DropdownMenuItem>
              <DropdownMenuItem variant="destructive" onSelect={onDelete}>
                <Trash2 /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </>
      ) : (
        !item.is_available && <Badge variant="outline">Unavailable</Badge>
      )}
    </div>
  );
}

export default function MenuPage() {
  const { tenant } = useAuth();
  const canEdit = tenant?.role === "owner";
  const queryClient = useQueryClient();
  const { categories, items } = useMenu();

  const [itemDialog, setItemDialog] = useState<{
    item: ItemOut | null;
    categoryId: string | null;
  } | null>(null);
  const [categoryDialog, setCategoryDialog] = useState<{ category: CategoryOut | null } | null>(
    null,
  );
  const [categoryName, setCategoryName] = useState("");
  const [confirm, setConfirm] = useState<
    { kind: "item"; item: ItemOut } | { kind: "category"; category: CategoryOut } | null
  >(null);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["menu"] });

  const reorder = useMutation({
    mutationFn: (body: object) => api<void>("/menu/reorder", { body }),
    onError: (err) => {
      toast.error(errorMessage(err));
      void refresh();
    },
  });

  const toggle = useMutation({
    mutationFn: ({ id, available }: { id: string; available: boolean }) =>
      api<ItemOut>(`/menu/items/${id}`, { method: "PATCH", body: { is_available: available } }),
    onMutate: ({ id, available }) => {
      queryClient.setQueryData<ItemOut[]>(["menu", "items"], (old) =>
        old?.map((i) => (i.id === id ? { ...i, is_available: available } : i)),
      );
    },
    onError: (err) => {
      toast.error(errorMessage(err));
      void refresh();
    },
  });

  const saveCategory = useMutation({
    mutationFn: ({ id, name }: { id: string | null; name: string }) =>
      id
        ? api<CategoryOut>(`/menu/categories/${id}`, { method: "PATCH", body: { name } })
        : api<CategoryOut>("/menu/categories", { body: { name } }),
    onSuccess: () => {
      setCategoryDialog(null);
      void refresh();
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  const remove = useMutation({
    mutationFn: (target: NonNullable<typeof confirm>) =>
      target.kind === "item"
        ? api<void>(`/menu/items/${target.item.id}`, { method: "DELETE" })
        : api<void>(`/menu/categories/${target.category.id}`, { method: "DELETE" }),
    onSuccess: () => {
      setConfirm(null);
      toast.success("Deleted");
      void refresh();
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  if (categories.isPending || items.isPending) return <Skeleton className="h-96 w-full" />;
  if (categories.isError || items.isError) {
    return <p className="text-destructive">{errorMessage(categories.error ?? items.error)}</p>;
  }

  const byCategory = new Map<string, ItemOut[]>();
  for (const item of items.data) {
    const key = item.category_id ?? UNCATEGORIZED;
    byCategory.set(key, [...(byCategory.get(key) ?? []), item]);
  }
  const sections: Section[] = categories.data.map((c) => ({
    id: c.id,
    category: c,
    items: byCategory.get(c.id) ?? [],
  }));
  const loose = byCategory.get(UNCATEGORIZED) ?? [];

  function reorderItems(sectionId: string, ordered: ItemOut[]) {
    const positions = new Map(ordered.map((item, index) => [item.id, index]));
    queryClient.setQueryData<ItemOut[]>(["menu", "items"], (old) =>
      old
        ?.map((i) => (positions.has(i.id) ? { ...i, position: positions.get(i.id)! } : i))
        .sort((a, b) => a.position - b.position),
    );
    reorder.mutate({ items: { [sectionId]: ordered.map((i) => i.id) } });
  }

  function reorderCategories(ordered: Section[]) {
    queryClient.setQueryData<CategoryOut[]>(["menu", "categories"], () =>
      ordered.map((s, index) => ({ ...s.category!, position: index })),
    );
    reorder.mutate({ categories: ordered.map((s) => s.id) });
  }

  function renderItems(sectionId: string, list: ItemOut[]) {
    if (list.length === 0) {
      return <p className="text-muted-foreground px-4 py-6 text-center text-sm">No items yet.</p>;
    }
    return (
      <SortableList
        items={list}
        disabled={!canEdit}
        onReorder={(ordered) => reorderItems(sectionId, ordered)}
        renderItem={(item, handle) => (
          <ItemRow
            item={item}
            handle={handle}
            canEdit={canEdit}
            onEdit={() => setItemDialog({ item, categoryId: item.category_id })}
            onToggle={(available) => toggle.mutate({ id: item.id, available })}
            onDelete={() => setConfirm({ kind: "item", item })}
          />
        )}
      />
    );
  }

  return (
    <>
      <PageHeader
        title="Menu"
        description={
          canEdit
            ? "Drag to reorder. Toggle availability when something sells out."
            : "View-only: ask an owner to change the menu."
        }
        actions={
          canEdit && (
            <>
              <Button
                variant="outline"
                onClick={() => {
                  setCategoryName("");
                  setCategoryDialog({ category: null });
                }}
              >
                <Plus /> Category
              </Button>
              <Button onClick={() => setItemDialog({ item: null, categoryId: null })}>
                <Plus /> Item
              </Button>
            </>
          )
        }
      />

      {sections.length === 0 && loose.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="font-medium">Your menu is empty</p>
            <p className="text-muted-foreground mt-1 text-sm">
              Start with a category like &ldquo;Cakes&rdquo;, then add items with prices.
            </p>
          </CardContent>
        </Card>
      )}

      <SortableList
        items={sections}
        disabled={!canEdit}
        onReorder={reorderCategories}
        className="grid gap-4"
        renderItem={(section, handle) => (
          <Card className="gap-0 overflow-hidden py-0">
            <CardHeader className="bg-muted/40 flex flex-row items-center gap-2 border-b px-2 py-2">
              {handle}
              <h2 className="flex-1 font-semibold">{section.category!.name}</h2>
              <span className="text-muted-foreground text-sm">{section.items.length}</span>
              {canEdit && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Actions for ${section.category!.name}`}
                    >
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      onSelect={() => setItemDialog({ item: null, categoryId: section.id })}
                    >
                      <Plus /> Add item here
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() => {
                        setCategoryName(section.category!.name);
                        setCategoryDialog({ category: section.category });
                      }}
                    >
                      <Pencil /> Rename
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      variant="destructive"
                      onSelect={() => setConfirm({ kind: "category", category: section.category! })}
                    >
                      <Trash2 /> Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </CardHeader>
            <CardContent className="px-0">{renderItems(section.id, section.items)}</CardContent>
          </Card>
        )}
      />

      {loose.length > 0 && (
        <Card className="mt-4 gap-0 overflow-hidden py-0">
          <CardHeader className="bg-muted/40 border-b px-4 py-3">
            <h2 className="font-semibold">Uncategorized</h2>
          </CardHeader>
          <CardContent className="px-0">{renderItems(UNCATEGORIZED, loose)}</CardContent>
        </Card>
      )}

      {itemDialog && (
        <ItemDialog
          open
          onOpenChange={(o) => !o && setItemDialog(null)}
          item={itemDialog.item}
          defaultCategoryId={itemDialog.categoryId}
          categories={categories.data}
        />
      )}

      <Dialog open={!!categoryDialog} onOpenChange={(o) => !o && setCategoryDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {categoryDialog?.category ? "Rename category" : "New category"}
            </DialogTitle>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (categoryName.trim())
                saveCategory.mutate({
                  id: categoryDialog?.category?.id ?? null,
                  name: categoryName.trim(),
                });
            }}
            className="grid gap-4"
          >
            <Input
              aria-label="Category name"
              value={categoryName}
              maxLength={100}
              autoFocus
              onChange={(e) => setCategoryName(e.target.value)}
              placeholder="e.g. Cakes"
            />
            <DialogFooter>
              <Button type="submit" disabled={!categoryName.trim() || saveCategory.isPending}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Delete {confirm?.kind === "item" ? confirm.item.name : confirm?.category.name}?
            </DialogTitle>
            <DialogDescription>
              {confirm?.kind === "category"
                ? "Items in this category will move to Uncategorized."
                : "It will disappear from your storefront. Past orders keep their details."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => confirm && remove.mutate(confirm)}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
