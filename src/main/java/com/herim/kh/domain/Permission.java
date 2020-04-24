package com.herim.kh.domain;

import java.util.List;

import javax.persistence.CascadeType;
import javax.persistence.Entity;
import javax.persistence.FetchType;
import javax.persistence.Id;
import javax.persistence.JoinColumn;
import javax.persistence.JoinTable;
import javax.persistence.ManyToMany;
import javax.persistence.ManyToOne;
import javax.persistence.OneToMany;

import lombok.Data;

@Data
@Entity(name = "permission")
public class Permission {

	@Id
	private String id;
	private String name;
	private String resourceType;
	private String url;
	private String permission;
	@ManyToOne
	@JoinColumn(name = "parent_id")
	private Permission parent;

	@OneToMany(fetch = FetchType.LAZY)
	@JoinColumn(name = "parent_id")
	private List<Permission> children;

	@ManyToMany
	@JoinTable(name = "user_permission", joinColumns = @JoinColumn(name = "permission_id"), inverseJoinColumns = @JoinColumn(name = "user_Id"))
	private List<User> users;

	@ManyToMany
	@JoinTable(name = "role_permission", joinColumns = {
			@JoinColumn(name = "permission_id") }, inverseJoinColumns = { @JoinColumn(name = "role_id") })
	private List<Role> roles;

}
