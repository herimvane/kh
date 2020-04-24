package com.herim.kh.domain;

import java.util.List;

import javax.persistence.CascadeType;
import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.FetchType;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.JoinColumn;
import javax.persistence.JoinTable;
import javax.persistence.ManyToMany;
import javax.persistence.ManyToOne;
import javax.persistence.OneToMany;
import javax.persistence.OneToOne;

import org.hibernate.annotations.GenericGenerator;

import lombok.Data;

/**
 * 人员表
 * @author herimvane
 *
 */
@Data
@Entity(name = "user")
public class User {

	@Id
	@GeneratedValue(generator = "uuid2")
    @GenericGenerator(name = "uuid2", strategy = "org.hibernate.id.UUIDGenerator")
	private String id;
	private String name;
	private String password;
	@Column(nullable=true)
	private Integer status;//0未生成任务；1已生成任务；2已完成打分
	
	@Column(nullable=true)
	private boolean sys;//是否为系统管理员
	
	@ManyToOne
	@JoinColumn(name = "position_id")
	private Position position;
	
	@ManyToOne
	@JoinColumn(name = "dept_id",nullable = true)
	private Dept dept;//所属部门
	
	@OneToMany(fetch = FetchType.LAZY)
	@JoinColumn(name = "leader")
	private List<Dept> deptsInLeader;//分管的部门
	
	@ManyToMany
	@JoinTable(name = "user_role", joinColumns = @JoinColumn(name="user_id"),inverseJoinColumns = @JoinColumn(name="role_id"))
	private List<Role> roles;
	
	@ManyToMany(fetch = FetchType.EAGER)
	@JoinTable(name = "user_permission",joinColumns = @JoinColumn(name = "user_id"),inverseJoinColumns = @JoinColumn(name = "permission_id"))
	private List<Permission> permissions;
}
