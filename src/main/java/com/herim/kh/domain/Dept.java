package com.herim.kh.domain;

import javax.persistence.CascadeType;
import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.FetchType;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.JoinColumn;
import javax.persistence.ManyToOne;
import javax.persistence.OneToOne;
import javax.persistence.Table;

import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.GenericGenerator;
import org.springframework.boot.context.properties.bind.DefaultValue;

import lombok.Data;

/**
 * 部门
 * @author herimvane
 *
 */
@Data
@Entity
@Table(name = "dept")
public class Dept {
	
	@Id
	@GeneratedValue(generator = "uuid2")
    @GenericGenerator(name = "uuid2", strategy = "org.hibernate.id.UUIDGenerator")
	private String id;
	private String name;
	
	
	@ManyToOne(fetch = FetchType.LAZY)
	@JoinColumn(name = "leader")
	private User leader;//分管领导
	
	@Column(nullable=true)
	@ColumnDefault("0")
	private float score;//部门得分

}
